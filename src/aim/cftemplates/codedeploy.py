import os
from aim.cftemplates.cftemplates import CFTemplate
from aim.cftemplates.cftemplates import Parameter
from aim.cftemplates.cftemplates import StackOutputParam
from io import StringIO
from enum import Enum


class CodeDeploy(CFTemplate):
    def __init__(self,
                 aim_ctx,
                 account_ctx,
                 subenv_ctx,
                 aws_name,
                 app_id,
                 grp_id,
                 res_id,
                 deploy_config,
                 artifacts_bucket_name,
                 cpbd_config_ref):

        #aim_ctx.log("S3 CF Template init")
        self.subenv_ctx = subenv_ctx
        super().__init__(aim_ctx,
                         account_ctx,
                         config_ref=cpbd_config_ref,
                         aws_name='-'.join(["CPBD-Deploy", aws_name]),
                         iam_capabilities=["CAPABILITY_NAMED_IAM"])

        self.resource_name = aim_ctx.normalized_join([self.subenv_ctx.get_aws_name(), app_id, grp_id, res_id],
                                                     '-',
                                                     False)
        self.application_name = self.resource_name

        # Initialize Parameters
        self.set_parameter('ResourceNamePrefix', self.resource_name)
        self.set_parameter('ApplicationName', self.application_name)
        self.set_parameter('CodeDeployASGName', deploy_config.asg_name)
        self.set_parameter('ELBName', deploy_config.elb_name)
        self.set_parameter('ALBTargetGroupName', deploy_config.alb_target_group_name)
        self.set_parameter('ArtifactsBucketName', artifacts_bucket_name)
        self.set_parameter('CodeDeployAutoRollbackEnabled', deploy_config.auto_rollback_enabled)
        self.set_parameter('CodeDeployConfigType', deploy_config.deploy_config_type)
        self.set_parameter('CodeDeployStyleOption', deploy_config.deploy_style_option)
        self.set_parameter('CodeDeployConfigValue', deploy_config.deploy_config_value)
        self.set_parameter('ToolsAccountId', deploy_config.tools_account)
        deploy_kms_ref = self.subenv_ctx.gen_ref( app_id=app_id,
                                                  grp_id=grp_id,
                                                  res_id=res_id,
                                                  attribute='kms')
        self.set_parameter('CMKArn', deploy_kms_ref)
        self.set_parameter('TargetInstanceRoleName', deploy_config.deploy_instance_role_name)

        # Define the Template
        template_fmt = """
AWSTemplateFormatVersion: '2010-09-09'
Description: 'Code Deploy'

Parameters:

  ResourceNamePrefix:
    Description: The name to prefix to AWS resources
    Type: String

  ApplicationName:
    Description: The name of the CodeDeploy Application
    Type: String

  ArtifactsBucketName:
    Description: The bname of the S3 Bucket to create that will hold deployment artifacts
    Type: String

  CodeDeployASGName:
    Description: The name of the AutoScaling Group of the deployment workload
    Type: String

  CodeDeployAutoRollbackEnabled:
    Description: Boolean indicating whether CodeDeploy will rollback a deployment if an error is encountered
    Type: String
    AllowedValues:
      - true
      - false

  CodeDeployConfigType:
    Description: The minimum healthy instance type HOST_COUNT or FLEET_PERCENT
    Type: String
    AllowedValues:
      - HOST_COUNT
      - FLEET_PERCENT

  CodeDeployStyleOption:
    Description: Either WITH_TRAFFIC_CONTROL or WITHOUT_TRAFFIC_CONTROL
    Type: String

  CodeDeployConfigValue:
    Description: The minimum number or percent of healthy hosts relevant to the chosen ConfigType
    Type: String

  ELBName:
    Description: The name of the ELB that will be managed by CodeDeploy during deployment
    Type: String

  ALBTargetGroupName:
    Description: The name of the target group that will be managed by CodeDeploy during deployment
    Type: String

  ToolsAccountId:
    Description: The AWS Account ID of the Tools account
    Type: String

  CMKArn:
    Description: The KMS CMK Arn of the key used to encrypt deployment artifacts
    Type: String

  TargetInstanceRoleName:
    Description: The ARN of the Role attached to the EC2 instance CodeDeploy deploys to
    Type: String

Conditions:
  ELBNameIsEmpty: !Equals [!Ref ELBName, ""]
  ALBTargetGroupNameIsEmpty: !Equals [!Ref ALBTargetGroupName, ""]

Resources:

# ----------------------------------------------------------------------------
# CodeDeploy

  ToolsDelegateRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Sub '${ResourceNamePrefix}-CodeDeploy-Tools-Delegate'
      AssumeRolePolicyDocument:
        Version: 2012-10-17
        Statement:
          - Effect: Allow
            Principal:
              AWS:
                - !Ref ToolsAccountId
            Action:
              - sts:AssumeRole
      Path: /
      Policies:
        - PolicyName: CodeDeploy
          PolicyDocument:
            Version: 2012-10-17
            Statement:
              - Effect: Allow
                Action:
                  - 'codedeploy:CreateDeployment'
                  - 'codedeploy:GetDeployment'
                  - 'codedeploy:GetDeploymentConfig'
                  - 'codedeploy:GetApplicationRevision'
                  - 'codedeploy:RegisterApplicationRevision'
                Resource:
                  - !Sub 'arn:aws:codedeploy:${AWS::Region}:${AWS::AccountId}:deploymentgroup:${ResourceNamePrefix}/*'
                  - !Sub 'arn:aws:codedeploy:${AWS::Region}:${AWS::AccountId}:application:${ResourceNamePrefix}'
                  - !Sub 'arn:aws:codedeploy:${AWS::Region}:${AWS::AccountId}:deploymentconfig:${ResourceNamePrefix}'
              - Sid: KMSCMK
                Effect: Allow
                Action:
                  - 'kms:DescribeKey'
                  - 'kms:GenerateDataKey*'
                  - 'kms:Encrypt'
                  - 'kms:ReEncrypt*'
                  - 'kms:Decrypt'
                Resource: !Ref CMKArn
              - Sid: S3ArtifactsBucket
                Effect: Allow
                Action:
                  - 's3:GetObject*'
                  - 's3:PutObject'
                  - 's3:PutObjectAcl'
                Resource:
                  - !Sub 'arn:aws:s3:::${ArtifactsBucketName}/*'

  CodeDeployServiceRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Sub '${ResourceNamePrefix}-CodeDeploy-Service'
      AssumeRolePolicyDocument:
        Version: 2012-10-17
        Statement:
          - Effect: Allow
            Principal:
              Service:
                - codedeploy.amazonaws.com
            Action:
              - sts:AssumeRole
      Path: /

  CodeDeployServicePolicy:
    Type: AWS::IAM::ManagedPolicy
    DependsOn:
      - CodeDeployServiceRole
    Properties:
      PolicyDocument:
        Version: 2012-10-17
        Statement:
          - Effect: Allow
            Action:
              - autoscaling:CompleteLifecycleAction
              - autoscaling:DeleteLifecycleHook
              - autoscaling:DescribeAutoScalingGroups
              - autoscaling:DescribeLifecycleHooks
              - autoscaling:PutLifecycleHook
              - autoscaling:RecordLifecycleActionHeartbeat
              - autoscaling:CreateAutoScalingGroup
              - autoscaling:UpdateAutoScalingGroup
              - autoscaling:EnableMetricsCollection
              - autoscaling:DescribeAutoScalingGroups
              - autoscaling:DescribePolicies
              - autoscaling:DescribeScheduledActions
              - autoscaling:DescribeNotificationConfigurations
              - autoscaling:DescribeLifecycleHooks
              - autoscaling:SuspendProcesses
              - autoscaling:ResumeProcesses
              - autoscaling:AttachLoadBalancers
              - autoscaling:PutScalingPolicy
              - autoscaling:PutScheduledUpdateGroupAction
              - autoscaling:PutNotificationConfiguration
              - autoscaling:PutLifecycleHook
              - autoscaling:DescribeScalingActivities
              - autoscaling:DeleteAutoScalingGroup
              - ec2:DescribeInstances
              - ec2:DescribeInstanceStatus
              - ec2:TerminateInstances
              - tag:GetTags
              - tag:GetResources
              - sns:Publish
              - cloudwatch:DescribeAlarms
              - cloudwatch:PutMetricAlarm
              - elasticloadbalancing:DescribeLoadBalancers
              - elasticloadbalancing:DescribeInstanceHealth
              - elasticloadbalancing:RegisterInstancesWithLoadBalancer
              - elasticloadbalancing:DeregisterInstancesFromLoadBalancer
              - elasticloadbalancing:DescribeTargetGroups
              - elasticloadbalancing:DescribeTargetHealth
              - elasticloadbalancing:RegisterTargets
              - elasticloadbalancing:DeregisterTargets
            Resource: "*"
      Roles:
        - !Ref CodeDeployServiceRole

  CodeDeployTargetInstancePolicy:
    Type: AWS::IAM::ManagedPolicy
    Properties:
      PolicyDocument:
        Version: 2012-10-17
        Statement:
          - Effect: Allow
            Action:
              - 'kms:DescribeKey'
              - 'kms:GenerateDataKey*'
              - 'kms:Encrypt'
              - 'kms:ReEncrypt*'
              - 'kms:Decrypt'
            Resource:
              - !Ref CMKArn
          - Effect: Allow
            Action:
              - s3:GetObject
            Resource:
              - !Sub 'arn:aws:s3:::${ArtifactsBucketName}/*'
              - !Sub 'arn:aws:s3:::aws-codedeploy-${AWS::Region}/*'
          - Effect: Allow
            Action:
              - 'autoscaling:DescribeAutoScalingGroups'
              - 'autoscaling:DescribeAutoScalingInstances'
            Resource:
              - '*' # XXX: Secure this
          - Effect: Allow
            Action:
              - 'autoscaling:UpdateAutoScalingGroup'
              - 'autoscaling:EnterStandby'
              - 'autoscaling:ExitStandby'
            Resource:
              - '*' # XXX: Secure this
      Roles:
        - !Ref TargetInstanceRoleName

  CodeDeployApplication:
    Type: AWS::CodeDeploy::Application
    Properties:
      ApplicationName: !Ref ApplicationName
      ComputePlatform: Server

  CodeDeployConfiguration:
    Type: AWS::CodeDeploy::DeploymentConfig
    Properties:
      DeploymentConfigName: !Ref ResourceNamePrefix
      MinimumHealthyHosts:
        Type: !Ref CodeDeployConfigType
        Value: !Ref CodeDeployConfigValue

  CodeDeployGroup:
    Type: AWS::CodeDeploy::DeploymentGroup
    DependsOn:
      - CodeDeployServicePolicy
      - CodeDeployServiceRole
      - CodeDeployApplication
      - CodeDeployConfiguration
    Properties:
      DeploymentGroupName: !Sub '${ResourceNamePrefix}-Group'
      ApplicationName: !Ref CodeDeployApplication
      AutoScalingGroups:
        - !Ref CodeDeployASGName
      AutoRollbackConfiguration:
        Enabled: !Ref CodeDeployAutoRollbackEnabled
        Events:
          - DEPLOYMENT_FAILURE
          - DEPLOYMENT_STOP_ON_ALARM
          - DEPLOYMENT_STOP_ON_REQUEST
      DeploymentConfigName: !Ref CodeDeployConfiguration
      ServiceRoleArn: !GetAtt CodeDeployServiceRole.Arn
      DeploymentStyle:
        DeploymentOption: !Ref CodeDeployStyleOption
        DeploymentType: IN_PLACE
      LoadBalancerInfo:
        ElbInfoList:
          !If
            - ELBNameIsEmpty
            - !Ref AWS::NoValue
            - - Name: !Ref ELBName
        TargetGroupInfoList:
          !If
            - ALBTargetGroupNameIsEmpty
            - !Ref AWS::NoValue
            - - Name: !Ref ALBTargetGroupName

Outputs:
  DeploymentGroupName:
     Value: !Ref CodeDeployGroup

"""

#        instance_policy_fmt = """
#          - Effect: {0[effect]:s}
#            Action: {0[action_list]:s}
#            Resource: "{0[resource_list]:s}" """
#
#        instance_policy_table = {
#            'effect': None,
#            'action_list': None,
#            'resource_list': None
#        }
#
#        policy_list_fmt = """
#              - '{0}'"""
#
#        template_table = {
#            'instance_policies': None
#        }
#
#        instance_policy_yaml = ""
#        for policy in deploy_config['deploy_instance_policy']['policies']:
#            instance_policy_table['effect'] = policy['effect']
#            action_yaml = ""
#            for action in policy['action']:
#                action_yaml += policy_list_fmt.format(action)
#            resource_yaml = ""
#            for resource in policy['resource']:
#                resource_yaml += policy_list_fmt.format(resource)
#            instance_policy_table['action_list'] = action_yaml
#            instance_policy_table['resource_list'] = resource_yaml
#            instance_policy_yaml += instance_policy_fmt.format(instance_policy_table)
#
#        template_table['instance_policies'] = instance_policy_yaml
#
#        self.set_template(template_fmt.format(template_table)
        self.set_template(template_fmt)

    def get_role_arn(self):
        account_id = self.account_ctx.get_id()
        return "arn:aws:iam::{0}:role/{1}-CodeDeploy-Service'".format(account_id, self.resource_name)

    def get_tools_delegate_role_arn(self):
        account_id = self.account_ctx.get_id()
        return "arn:aws:iam::{0}:role/{1}-CodeDeploy-Tools-Delegate".format(account_id, self.resource_name)

    def get_application_name(self):
        return self.application_name

    def validate(self):
        #self.aim_ctx.log("Validating CodeDeploy Template")
        super().validate()

    def get_outputs_key_from_ref(self, aim_ref):
        return "DeploymentGroupName"