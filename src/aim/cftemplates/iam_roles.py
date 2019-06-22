import os
from aim.cftemplates.cftemplates import CFTemplate
from aim.cftemplates.cftemplates import Parameter
from aim.cftemplates.cftemplates import StackOutputParam
from io import StringIO
from enum import Enum
import sys


class IAMRoles(CFTemplate):
    def __init__(self,
                 aim_ctx,
                 account_ctx,
                 iam_context_id,
                 roles_by_order):
        #aim_ctx.log("IAMRoles CF Template init")
        aws_name = "Roles"

        super().__init__(aim_ctx,
                         account_ctx,
                         config_ref="",
                         aws_name=aws_name,
                         iam_capabilities=["CAPABILITY_NAMED_IAM"])

        self.roles_by_order = roles_by_order
        self.iam_context_id = iam_context_id

        # Define the Template
        template_fmt = """
AWSTemplateFormatVersion: '2010-09-09'
Description: 'IAM Roles: Roles and Instance Profiles'

Parameters:
{0[parameters_yaml]:s}

Resources:
{0[resources_yaml]:s}

Outputs:
{0[outputs_yaml]:s}
"""
        template_table = {
            'parameters_yaml': "",
            'resources_yaml': "",
            'outputs_yaml': ""
        }

        iam_role_params_fmt ="""
  {0[role_path_param_name]:s}:
    Type: String
    Description: 'The path associated with the {0[role_path_param_name]:s} IAM Role'
    Default: '/'
"""

        iam_role_fmt = """
  {0[cf_resource_name_prefix]:s}Role:
    Type: AWS::IAM::Role
    Properties:
      Path: !Ref {0[role_path_param_name]:s}
      RoleName: {0[role_name]:s}
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: "Allow"
            Principal:{0[assume_role_principal]:s}
            Action:
              - "sts:AssumeRole"
{0[inline_policies]:s}

{0[instance_profile]:s}
"""
        iam_role_table = {
            'role_name': None,
            'instance_profile': None,
            'profile_name': None,
            'cf_resource_name_prefix': None,
            'inline_policies': ""
        }

        iam_profile_fmt = """
  {0[cf_resource_name_prefix]:s}InstanceProfile:
    Type: AWS::IAM::InstanceProfile
    Properties:
      Path: !Ref {0[role_path_param_name]:s}
      InstanceProfileName: {0[profile_name]:s}
      Roles:
        - !Ref {0[cf_resource_name_prefix]:s}Role

"""
        iam_role_outputs_fmt = """
  {0[cf_resource_name_prefix]:s}Role:
    Value: !Ref {0[cf_resource_name_prefix]:s}Role
"""

        iam_profile_outputs_fmt = """
  {0[cf_resource_name_prefix]:s}InstanceProfile:
    Value: !Ref {0[cf_resource_name_prefix]:s}InstanceProfile
"""

        parameters_yaml = ""
        resources_yaml = ""
        outputs_yaml = ""

        # Parameters
        parameter_fmt = """
  {0[key]:s}:
     Type: {0[type]:s}
     Description: {0[description]:s}
"""
        roles_yaml = ""
        iam_role_table.clear()
        for role_context in self.roles_by_order:
            if role_context['template_params']:
                for param_table in role_context['template_params']:
                    self.set_parameter(param_table['key'], param_table['value'])
                    parameters_yaml += parameter_fmt.format(param_table)

            role_config = role_context['config']
            role_id = role_context['id']

            # Role
            role_path_param_name = self.get_cf_resource_name_prefix(role_id) + "RolePath"
            iam_role_table['role_path_param_name'] = role_path_param_name
            iam_role_table['role_name'] = self.gen_iam_role_name("Role", role_id)
            iam_role_table['cf_resource_name_prefix'] = self.get_cf_resource_name_prefix(role_id)

            # Assume Role Principal
            principal_yaml = ""
            if role_config.assume_role_policy != None:
                if len(role_config.assume_role_policy.service) > 0:
                    principal_yaml += """
              Service:"""
                    for service_item in role_config.assume_role_policy.service:
                        principal_yaml += """
                - """ + service_item
                elif role_config.assume_role_policy.aws != '':
                    principal_yaml += """
              AWS:"""
                    for aws_item in role_config.assume_role_policy.aws:
                        principal_yaml += """
                - """ + aws_item
            else:
                pass
            iam_role_table['assume_role_principal'] = principal_yaml

            if role_config.policies:
                iam_role_table['inline_policies'] = self.gen_role_policies(role_config.policies)
            else:
                iam_role_table['inline_policies'] = ""

            # Instance Profile
            if role_config.instance_profile == True:
                iam_role_table['profile_name'] = self.gen_iam_role_name("Profile", role_id)
                iam_role_table['instance_profile'] = iam_profile_fmt.format(iam_role_table)
            else:
                iam_role_table['instance_profile'] = ""

            parameters_yaml += iam_role_params_fmt.format(iam_role_table)
            resources_yaml += iam_role_fmt.format(iam_role_table)
            outputs_yaml += iam_role_outputs_fmt.format(iam_role_table)

            if role_config.instance_profile == True:
                outputs_yaml += iam_profile_outputs_fmt.format(iam_role_table)
            # Initialize Parameters
            self.set_parameter(role_path_param_name, role_config.path)

        template_table['parameters_yaml'] = parameters_yaml
        template_table['resources_yaml'] = resources_yaml
        template_table['outputs_yaml'] = outputs_yaml
        self.set_template(template_fmt.format(template_table))

    def validate(self):
        #self.aim_ctx.log("Validating IAM Roles Template")
        super().validate()

    # Generate a name valid in CloudFormation
    def gen_iam_role_name(self, role_type, role_id):
        iam_context_hash = self.aim_ctx.md5sum(str_data=self.iam_context_id)[:8].upper()
        role_name = '-'.join([iam_context_hash, role_type[0], role_id])
        role_name = self.aim_ctx.normalize_name(role_name, '-', False)
        return role_name

    def get_cf_resource_name_prefix(self, resource_name):
        norm_res_name = self.aim_ctx.normalize_name(resource_name, '', True)
        return norm_res_name.replace('-', '')

    def gen_role_policies(self, policies):

        policies_yaml = "      Policies:"
        policy_fmt = """
        - PolicyName: {0[name]:s}
          PolicyDocument:
            Version: 2012-10-17
            Statement:{0[statement_list]:s}
"""
        policy_table = {
            'name': None,
            'statement_list': None
        }

        statement_fmt = """
              - Effect: {0[effect]:s}
                Action:{0[action_list]:s}
                Resource:{0[resource_list]:s}
"""
        statement_table = {
            'effect': None,
            'action_list': None,
            'resource_list': None
        }

        quoted_list_fmt = """
                  - '{0}'"""
        unquoted_list_fmt = """
                  - {0}"""
        for inline_policy in policies:
            policy_table['name'] = ""
            policy_table['statement_list'] = ""
            policy_table['name'] = inline_policy.name
            for statement in inline_policy.statement:
                statement_table['effect'] = ""
                statement_table['action_list'] = ""
                statement_table['resource_list'] = ""
                statement_table['effect'] = statement.effect
                for action in statement.action:
                    statement_table['action_list'] += quoted_list_fmt.format(action)
                for resource in statement.resource:
                    if resource[0:1] == '!':
                        statement_table['resource_list'] += unquoted_list_fmt.format(resource)
                    else:
                        statement_table['resource_list'] += quoted_list_fmt.format(resource)

                policy_table['statement_list'] += statement_fmt.format(statement_table)

            policies_yaml += policy_fmt.format(policy_table)

        return policies_yaml

    def get_role_arn_from_id(self, role_id):
        role_name = self.gen_iam_role_name("Role", role_id)
        return "arn:aws:iam::{0}:role/{1}".format(self.account_ctx.get_id(), role_name)

    def get_role_arn_from_ref(self, ref_dict):
        role_id = ref_dict['ref_parts'][6]
        role_name = self.gen_iam_role_name("Role", role_id)
        return "arn:aws:iam::{0}:role/{1}".format(self.account_ctx.get_id(), role_name)
