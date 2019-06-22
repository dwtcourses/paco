import os
from aim.cftemplates.cftemplates import CFTemplate
from aim.cftemplates.cftemplates import Parameter
from aim.cftemplates.cftemplates import StackOutputParam
from io import StringIO
from enum import Enum
from pprint import pprint

class ALB(CFTemplate):
    def __init__(self, aim_ctx,
                 account_ctx,
                 subenv_ctx,
                 aws_name,
                 app_id,
                 alb_id,
                 alb_config,
                 alb_config_ref):
        #aim_ctx.log("ALB CF Template init")
        self.subenv_ctx = subenv_ctx
        self.alb_config_ref = alb_config_ref
        segment_stack = self.subenv_ctx.get_segment_stack(alb_config.segment)

        super().__init__(aim_ctx=aim_ctx,
                         account_ctx=account_ctx,
                         config_ref=alb_config_ref,
                         aws_name='-'.join([ "ALB", aws_name]))


        # Initialize Parameters
        self.set_parameter('ALBEnabled', alb_config.enabled)
        vpc_stack = self.subenv_ctx.get_vpc_stack()
        self.set_parameter(StackOutputParam('VPC', vpc_stack, 'VPC'))
        self.set_parameter('CustomDomainName', getattr(alb_config.dns, 'domain_name', ''))
        self.set_parameter('HostedZoneId', getattr(alb_config.dns, 'hosted_zone_id', ''))

        alb_region = subenv_ctx.region
        self.set_parameter('ALBHostedZoneId', self.lb_hosted_zone_id('alb', alb_region))

        # 32 Characters max
        # <proj>-<env>-<app>-<alb_id>
        # TODO: Limit each name item to 7 chars
        # Name collision risk:, if unique identifying characrtes are truncated
        #   - Add a hash?
        #   - Check for duplicates with validating template
        # TODO: Make a method for this
        #load_balancer_name = aim_ctx.project_ctx.name + "-" + aim_ctx.env_ctx.name + "-" + stack_group_ctx.application_name + "-" + alb_id
        load_balancer_name = aim_ctx.normalized_join([self.subenv_ctx.netenv_id, self.subenv_ctx.subenv_id, app_id, alb_id],
                                                     '',
                                                     True)
        self.set_parameter('LoadBalancerName', load_balancer_name)

        self.set_parameter('Scheme', alb_config.scheme)

        # Segment SubnetList is a Segment stack Output based on availability zones
        subnet_list_key = 'SubnetList' + str(self.subenv_ctx.availability_zones())

        self.set_parameter(StackOutputParam('SubnetList', segment_stack, subnet_list_key))

        # Security Group List
        sg_output_param = StackOutputParam('SecurityGroupList')
        for sg_ref in alb_config.security_groups:
            # TODO: Better name for self.get_stack_outputs_key_from_ref?
            # print("ALB: SG_REF: " + sg_ref)
            sg_output_key = self.get_stack_outputs_key_from_ref(sg_ref)
            sg_stack = self.aim_ctx.get_ref(sg_ref, 'stack')
            sg_output_param.add_stack_output(sg_stack, sg_output_key)
        self.set_parameter(sg_output_param)

        # Define the Template
        template_fmt = """
AWSTemplateFormatVersion: '2010-09-09'
Description: 'Application Load Balancer'

Parameters:

  ALBEnabled:
    Type: String
    Default: False
    AllowedValues:
      - true
      - false

  VPC:
    Description: VPC ID
    Type: String

  LoadBalancerName:
    Description: The name of the load balancer
    Type: String

  Scheme:
    Description: 'Specify internal to create an internal load balancer with a DNS name that resolves to private IP addresses or internet-facing to create a load balancer with a publicly resolvable DNS name, which resolves to public IP addresses.'
    Type: String
    MinLength: '1'
    MaxLength: '128'

  SubnetList:
    Description: A list of subnets where the ALBs instances will be provisioned
    Type: List<AWS::EC2::Subnet::Id>

  SecurityGroupList:
    Description: A List of security groups to attach to the ALB
    Type: List<AWS::EC2::SecurityGroup::Id>

  CustomDomainName:
    Description: Custom DNS name to assign to the ALB
    Type: String
    Default: ""

  HostedZoneId:
    Description: The Route53 Hosted Zone ID where the Custom Domain will be added
    Type: String

  ALBHostedZoneId:
    Description: The Regonal AWS Route53 Hosted Zone ID
    Type: String

{0[RecordSetsParameters]:s}

{0[SSLCertificateParameters]:s}

Conditions:
  CustomDomainIsEnabled: !Not [!Equals [!Ref CustomDomainName, ""] ]
  ALBIsEnabled: !Equals [!Ref ALBEnabled, "true"]

Resources:

# Elastic Load Balancer

  LoadBalancer:
    Type: AWS::ElasticLoadBalancingV2::LoadBalancer
    Condition: ALBIsEnabled
    Properties:
      Name: !Ref LoadBalancerName
      Subnets: !Ref SubnetList
      Scheme: !Ref Scheme
      SecurityGroups: !Ref SecurityGroupList
      Type: application

{0[RecordSets]:s}

{0[Listeners]:s}

{0[TargetGroups]:s}

Outputs:
  LoadBalancerName:
    Condition: ALBIsEnabled
    Value: !GetAtt LoadBalancer.LoadBalancerName

  LoadBalancerFullName:
    Condition: ALBIsEnabled
    Value: !GetAtt LoadBalancer.LoadBalancerFullName

  LoadBalancerArn:
    Condition: ALBIsEnabled
    Value: !Ref LoadBalancer

  LoadBalancerCanonicalHostedZoneID:
    Condition: ALBIsEnabled
    Value: !GetAtt LoadBalancer.CanonicalHostedZoneID

{0[TargetGroupOutputs]:s}
"""

        record_set_fmt = """
  RecordSet{0[idx]:d}:
    Type: AWS::Route53::RecordSet
    Condition: ALBIsEnabled
    Properties:
      HostedZoneId: !Ref HostedZoneID{0[idx]:d}
      Name: {0[domain_name]:s}
      Type: A
      AliasTarget:
        DNSName: !GetAtt LoadBalancer.DNSName
        HostedZoneId: !GetAtt LoadBalancer.CanonicalHostedZoneID"""

        record_set_table = {
          'hosted_zone_id': None,
          'domain_name': None
        }

        record_set_param_fmt = """
  HostedZoneID{0[idx]:d}:
     Description: Hozed Zone ID for RecordSet{0[idx]:d}
     Type: String
"""

        ssl_cert_param_fmt = """
  SSLCertificateIdL{0[listener_idx]:d}C{0[cert_idx]:d}:
    Description: The Arn of the SSL Certificate to associate with this Load Balancer
    Type: String
"""

        ssl_certificate_list_fmt = """
        - CertificateArn: !Ref SSLCertificateIdL{0[listener_idx]:d}C{0[cert_idx]:d}"""

        ssl_certificate_table = {
            'listener_idx': 0,
            'cert_idx': 0
        }


        forward_action_fmt = """
        - Type: forward
          TargetGroupArn: !Ref TargetGroup{0[target_group_id]:s}"""

        redirect_action_fmt = """
        - Type: redirect
          RedirectConfig:
            Port: {0[port]:d}
            Protocol: {0[protocol]:s}
            StatusCode: HTTP_301"""

        default_action_table = {
            'target_group_id': None,
            'port': None,
            'protocol': None
        }

        listener_fmt = """
  Listener{0[idx]:d}:
    Type: AWS::ElasticLoadBalancingV2::Listener
    Condition: ALBIsEnabled
    Properties:
      DefaultActions: {0[default_actions]:s}
      LoadBalancerArn: !Ref LoadBalancer
      Port: {0[port]:d}
      Protocol: {0[protocol]:s}
{0[ssl_certificates]:s}

{0[listener_certificate]:s}
"""

        listener_certificate_fmt = """
  Listener{0[idx]:d}Certificate:
    Type: AWS::ElasticLoadBalancingV2::ListenerCertificate
    Condition: ALBIsEnabled
    Properties:
      Certificates: {0[ssl_listener_cert_list]:s}
      ListenerArn : !Ref Listener{0[idx]:d}
"""

        listener_table = {
            'idx': None,
            'port': None,
            'protocol': None,
            'ssl_certificates': None,
            'default_actions': None,
            'listener_certificate': None,
            'ssl_listener_cert_list': None
        }

        listener_forward_rule_fmt = """
  Listener{0[listener_idx]:d}Rule{0[rule_idx]:d}:
    Type: AWS::ElasticLoadBalancingV2::ListenerRule
    Condition: ALBIsEnabled
    Properties:
      Actions:
        - Type: forward
          TargetGroupArn: !Ref TargetGroup{0[target_group_id]:s}
      Conditions:
        - Field: host-header
          Values:
            - '{0[host_value]:s}'
      ListenerArn: !Ref Listener{0[listener_idx]:d}
      Priority: {0[priority]:d}
"""
        listener_forward_rule_table = {
            'listener_idx': 0,
            'rule_idx': 0,
            'target_group_id': None,
            'host_value': None,
            'priority': 0
        }

        target_group_fmt = """
  TargetGroup{0[id]:s}:
    Type: AWS::ElasticLoadBalancingV2::TargetGroup
    Properties:
      Name: {0[name]:s}
      HealthCheckIntervalSeconds: {0[health_check_interval]:d}
      HealthCheckTimeoutSeconds: {0[health_check_timeout]:d}
      HealthyThresholdCount: {0[healthy_threshold]:d}
      HealthCheckPath: {0[health_check_path]:s}
      Port: {0[port]:d}
      Protocol: {0[protocol]:s}
      UnhealthyThresholdCount: {0[unhealthy_threshold]:d}
      TargetGroupAttributes:
        - Key: 'deregistration_delay.timeout_seconds'
          Value: {0[connection_drain_timeout]:d}
      Matcher:
        HttpCode: {0[health_check_http_code]:d}
      VpcId: !Ref VPC
"""

        target_group_table = {
            'id': None,
            'name': None,
            'port': None,
            'protocol': None,
            'health_check_path': None,
            'health_check_interval': None,
            'health_check_timeout': None,
            'healthy_threshold': None,
            'unhealthy_threshold': None,
            'connection_drain_timeout': None,
            'health_check_http_code': None
        }


        ssl_certificate_fmt = """
      Certificates:"""

        target_group_outputs_fmt = """
  TargetGroupArn{0[id]:s}:
    Value: !Ref TargetGroup{0[id]:s}

  TargetGroupName{0[id]:s}:
    Value: !GetAtt TargetGroup{0[id]:s}.TargetGroupName
"""

        #print("------------------")
        listener_yaml = ""
        ssl_cert_param_yaml = ""
        listener_idx = 0
        for listener in alb_config.listeners:
            listener_table['idx'] = listener_idx
            listener_table['port'] = listener.port
            listener_table['protocol'] = listener.protocol
            if listener.redirect != None:
                default_action_table['port'] = listener.redirect.port
                default_action_table['protocol'] = listener.redirect.protocol
                listener_table['default_actions'] = redirect_action_fmt.format(default_action_table)
            else:
                default_action_table['target_group_id'] = listener.target_group
                listener_table['default_actions'] = forward_action_fmt.format(default_action_table)



            # Listener SSL Certificates
            listener_table['ssl_certificates'] = ""
            listener_table['listener_certificate'] = ""
            listener_table['ssl_listener_cert_list'] = ""
            if len(listener.ssl_certificates) > 0:
                listener_table['ssl_certificates'] = ssl_certificate_fmt
                ssl_certificate_table['cert_idx'] = 0
                ssl_certificate_table['listener_idx'] = listener_idx
                listener_table['ssl_certificates'] += ssl_certificate_list_fmt.format(ssl_certificate_table)
                for ssl_cert_idx in range(0, len(listener.ssl_certificates)):
                    ssl_certificate_table['cert_idx'] = ssl_cert_idx
                    listener_table['ssl_listener_cert_list'] += ssl_certificate_list_fmt.format(ssl_certificate_table)
                    #print(listener_yaml)
                    ssl_cert_param_yaml += ssl_cert_param_fmt.format(ssl_certificate_table)
                    self.set_parameter('SSLCertificateIdL%dC%d' % (listener_idx, ssl_cert_idx),listener.ssl_certificates[ssl_cert_idx])
                listener_table['listener_certificate'] = listener_certificate_fmt.format(listener_table)
            # Listener
            listener_yaml += listener_fmt.format(listener_table)

            # Listener Rules
            listener_forward_rule_table['rule_idx'] = 0
            for forward in listener.forward_hosts:
              listener_forward_rule_table['listener_idx'] = listener_idx
              listener_forward_rule_table['target_group_id'] = forward.target_group
              listener_forward_rule_table['host_value'] = forward.host
              listener_forward_rule_table['priority'] = forward.priority
              listener_yaml += listener_forward_rule_fmt.format(listener_forward_rule_table)
              listener_forward_rule_table['rule_idx'] += 1
            listener_idx += 1
        #print("------------------")
        #print(listener_yaml)
        #print("------------------")

        target_group_yaml = ""
        target_group_outputs_yaml = ""
        for target_group_id in sorted(alb_config.target_groups.keys()):
            target_config = alb_config.target_groups[target_group_id]
            target_group_table['id'] = self.normalize_resource_name(target_group_id)
            target_group_table['name'] = load_balancer_name + target_group_id
            target_group_table['port'] = target_config.port
            target_group_table['protocol'] = target_config.protocol
            target_group_table['health_check_path'] = target_config.health_check_path
            target_group_table['health_check_interval'] = target_config.health_check_interval
            target_group_table['health_check_timeout'] = target_config.health_check_timeout
            target_group_table['healthy_threshold'] = target_config.healthy_threshold
            target_group_table['unhealthy_threshold'] = target_config.unhealthy_threshold
            target_group_table['health_check_http_code'] = target_config.health_check_http_code
            target_group_table['connection_drain_timeout'] = target_config.connection_drain_timeout
            # print(target_group_table)
            target_group_yaml += target_group_fmt.format(target_group_table)
            target_group_ref = '.'.join([alb_config_ref, 'target_groups', target_group_id])
            target_group_arn_ref = '.'.join([target_group_ref, 'arn'])
            self.register_stack_output_config(target_group_arn_ref, 'TargetGroupArn'+target_group_table['id'])
            target_group_name_ref = '.'.join([target_group_ref, 'name'])
            self.register_stack_output_config(target_group_name_ref, 'TargetGroupName'+target_group_table['id'])
            target_group_outputs_yaml += target_group_outputs_fmt.format(target_group_table)

        # Record Sets
        record_sets_yaml = ""
        record_sets_param_yaml = ""
        record_set_table['idx'] = 0
        for alb_dns in alb_config.dns:
            record_set_table['hosted_zone_id'] = alb_dns.hosted_zone_id
            record_set_table['domain_name'] = alb_dns.domain_name
            self.set_parameter('HostedZoneID%d' % (record_set_table['idx']), alb_dns.hosted_zone_id)
            record_sets_yaml += record_set_fmt.format(record_set_table)
            record_sets_param_yaml += record_set_param_fmt.format(record_set_table)
            record_set_table['idx'] += 1

        template_fmt_table = {
            'Listeners': listener_yaml,
            'TargetGroups': target_group_yaml,
            'SSLCertificateParameters': ssl_cert_param_yaml,
            'TargetGroupOutputs': target_group_outputs_yaml,
            'RecordSets': record_sets_yaml,
            'RecordSetsParameters': record_sets_param_yaml
        }

        self.set_template(template_fmt.format(template_fmt_table))
        if alb_config.enabled:
          self.register_stack_output_config(self.alb_config_ref+'.arn', 'LoadBalancerArn')
          self.register_stack_output_config(self.alb_config_ref+'.name', 'LoadBalancerName')
          self.register_stack_output_config(self.alb_config_ref+'.fullname', 'LoadBalancerFullName')
          self.register_stack_output_config(self.alb_config_ref+'.canonicalhostedzoneid', 'LoadBalancerCanonicalHostedZoneID')

    def validate(self):
        #self.aim_ctx.log("Validating ALB Template")
        super().validate()

    def get_outputs_key_from_ref(self, aim_ref):
        # There is only one output key
        # netenv.ref wbsites.applications.sites.resources.alb.target_groups.app.arn
        ref_dict = self.aim_ctx.parse_ref(aim_ref)
        last_idx = len(ref_dict['ref_parts'])-1
        key = None
        #print(aim_ref)
        if ref_dict['ref_parts'][last_idx] == 'arn':
            key = "TargetGroupArn" + ref_dict['ref_parts'][last_idx-1]
        elif ref_dict['ref_parts'][last_idx] == 'name':
            key = "TargetGroupName" + ref_dict['ref_parts'][last_idx-1]

        #print("alb: get_outputs_key_from_ref: Key: " + key)
        return key