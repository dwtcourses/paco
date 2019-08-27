import os
from aim.cftemplates.cftemplates import CFTemplate
from aim.cftemplates.cftemplates import Parameter
from aim.cftemplates.cftemplates import StackOutputParam
from aim.utils import md5sum, normalize_name
from io import StringIO
from enum import Enum
import sys


class IAMManagedPolicies(CFTemplate):
    def __init__(self,
                 aim_ctx,
                 account_ctx,
                 aws_region,
                 stack_group,
                 stack_tags,
                 policy_context,
                 template_name):
        #aim_ctx.log("IAMManagedPolicies CF Template init")
        aws_name = '-'.join([template_name, "Policy"])

        super().__init__(
            aim_ctx,
            account_ctx,
            aws_region,
            enabled=policy_context['config'].is_enabled(),
            config_ref="",
            aws_name=aws_name,
            iam_capabilities=["CAPABILITY_NAMED_IAM"],
            stack_group=stack_group,
            stack_tags=stack_tags
        )
        self.policy_context = policy_context
        # Define the Template
        template_fmt = """
AWSTemplateFormatVersion: '2010-09-09'
Description: 'IAM Roles: Roles and Instance Profiles'

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

        policy_fmt = """
  {0[cf_resource_name_prefix]:s}ManagedPolicy:
    Type: AWS::IAM::ManagedPolicy
    Properties:
      #Description: String
      #Groups:
      #  - String
      ManagedPolicyName: {0[name]:s}
      Path: {0[path]:s}
{0[policy_document]}
{0[statement]}
{0[roles]}
{0[users]}
"""
        policy_document = """
      PolicyDocument:
        Version: "2012-10-17"
        Statement:"""

        policy_table = {
            'name': None,
            'path': None,
            'cf_resource_name_prefix': None,
            'policy_document': None,
            'statement': None,
            'roles': None,
            'users': None
        }

        role_fmt = """        - %s
"""
        user_fmt = """        - %s
"""

        policy_outputs_fmt = """
  {0[cf_resource_name_prefix]:s}ManagedPolicy:
    Value: !Ref {0[cf_resource_name_prefix]:s}ManagedPolicy
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
        policy_table.clear()
        if policy_context['template_params']:
            for param_table in policy_context['template_params']:
                self.set_parameter(param_table['key'], param_table['value'])
                parameters_yaml += parameter_fmt.format(param_table)

        policy_config = policy_context['config']
        policy_id = policy_context['id']
        # Name
        policy_table['name'] = self.gen_policy_name(policy_id)
        policy_table['cf_resource_name_prefix'] = self.get_cf_resource_name_prefix(policy_id)
        # Path
        policy_table['path'] = policy_config.path

        # Policy Document
        if policy_config.is_enabled() == True:
            # Roles
            policy_table['roles'] = ""
            if policy_config.roles and len(policy_config.roles) > 0:
                policy_table['roles'] = """      Roles:
    """
                for role in policy_config.roles:
                    policy_table['roles'] += role_fmt % (role)

            # Users
            policy_table['users'] = ""
            if policy_config.users and len(policy_config.users) > 0:
                policy_table['users'] = """      Users:
    """
                for user in policy_config.users:
                    policy_table['users'] += user_fmt % (user)

            policy_table['policy_document'] = policy_document
            # Statement
            policy_table['statement'] = self.gen_statement_yaml(policy_config.statement)
        else:
            policy_table['statement'] = ""
            policy_table['policy_document'] = ""
            policy_table['roles'] = ""
            policy_table['users'] = ""

        # Initialize Parameters
        # Resources
        resources_yaml += policy_fmt.format(policy_table)
        # Outputs
        outputs_yaml += policy_outputs_fmt.format(policy_table)

        template_table['parameters_yaml'] = ""
        if parameters_yaml != "":
            template_table['parameters_yaml'] = """Parameters:
"""
        template_table['parameters_yaml'] += parameters_yaml
        template_table['resources_yaml'] = resources_yaml
        template_table['outputs_yaml'] = outputs_yaml
        self.set_template(template_fmt.format(template_table))


    # Generate a name valid in CloudFormation
    def gen_policy_name(self, policy_id):
        policy_context_hash = md5sum(str_data=self.policy_context['ref'])[:8].upper()
        policy_name = '-'.join([policy_context_hash, policy_id])
        policy_name = normalize_name(policy_name, '-', False)
        return policy_name

    def get_cf_resource_name_prefix(self, resource_name):
        norm_res_name = normalize_name(resource_name, '', True)
        return norm_res_name.replace('-', '')

    # TODO: This shares the same code in iam_roles.py. This should
    # be consolidated in cftemplates.py...
    def gen_statement_yaml(self, statements):
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
        statement_yaml = ""
        for statement in statements:
            statement_table['effect'] = ""
            statement_table['action_list'] = ""
            statement_table['resource_list'] = ""
            statement_table['effect'] = statement.effect
            statement_table['principal'] = ""
            statement_table['condition'] = ""
            for action in statement.action:
                statement_table['action_list'] += quoted_list_fmt.format(action)
            for resource in statement.resource:
                if resource[0:1] == '!':
                    statement_table['resource_list'] += unquoted_list_fmt.format(resource)
                else:
                    statement_table['resource_list'] += quoted_list_fmt.format(resource)

            statement_yaml += statement_fmt.format(statement_table)

        return statement_yaml
