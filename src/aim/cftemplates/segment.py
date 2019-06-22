import os
from aim.cftemplates.cftemplates import CFTemplate
from aim.cftemplates.cftemplates import Parameter
from aim.cftemplates.cftemplates import StackOutputParam
from io import StringIO
from enum import Enum

class Segment(CFTemplate):
    def __init__(self,
                 aim_ctx,
                 account_ctx,
                 subenv_ctx,
                 segment_id,
                 segment_config,
                 segment_config_ref):

        #aim_ctx.log("Segment CF Template init")
        self.subenv_ctx = subenv_ctx
        # Super
        super().__init__(aim_ctx,
                         account_ctx,
                         config_ref=segment_config_ref,
                         aws_name='-'.join(["Segments", segment_id]))

        vpc_stack = self.subenv_ctx.get_vpc_stack()
        availability_zones = self.subenv_ctx.availability_zones()

        # Initialize Parameters
        # VPC
        self.set_parameter(StackOutputParam('VPC', vpc_stack, 'VPC'))

        # Internet Gateway
        self.set_parameter(StackOutputParam('InternetGateway', vpc_stack, 'InternetGateway'))

        # Subnet CIDRS
        self.set_parameter('SubnetAZ1CIDR', segment_config.az1_cidr)
        if segment_config.az2_cidr != '' and availability_zones > 1:
            self.set_parameter('SubnetAZ2CIDR', segment_config.az2_cidr)
        if segment_config.az3_cidr != '' and availability_zones > 2:
            self.set_parameter('SubnetAZ3CIDR', segment_config.az3_cidr)

        # Public Subnet boolean
        if segment_config.internet_access != '':
            self.set_parameter('IsPublicCondition', segment_config.internet_access)
        else:
            self.set_parameter('IsPublicCondition', 'false')
        # Define the Template
        self.set_template("""
AWSTemplateFormatVersion: '2010-09-09'
Description: 'Segment: NACLs, RouteTables, Subnets'

#------------------------------------------------------------------------------
Parameters:
  VPC:
    Description: 'VPC ID'
    Type: String

  InternetGateway:
    Description: 'The Internet Gateway ID'
    Type: String
    Default: 'novalue'

  SubnetAZ1CIDR:
    Description: 'AZ1 - CIDR for the Subnet'
    Type: String

  SubnetAZ2CIDR:
    Description: 'AZ2 - CIDR for the Subnet'
    Type: String
    Default: 'novalue'

  SubnetAZ3CIDR:
    Description: 'AZ3 - CIDR for the Subnet'
    Type: String
    Default: 'novalue'

  IsPublicCondition:
    Description: 'If true, adds a default route to the Internet Gateway'
    Type: String
    AllowedValues:
      - true
      - false

#------------------------------------------------------------------------------
Conditions:
  IsPublic: !Equals [ !Ref IsPublicCondition, 'true' ]

  AZ2Disabled: !Equals [ !Ref SubnetAZ2CIDR, 'novalue' ]
  AZ2Enabled: !Not [ Condition: AZ2Disabled ]
  AZ2EnabledAndIsPublic: !And
    - !Condition AZ2Enabled
    - !Condition IsPublic


  AZ3Disabled: !Equals [ !Ref SubnetAZ3CIDR, 'novalue' ]
  AZ3Enabled: !Not [ Condition: AZ3Disabled ]
  AZ3EnabledAndIsPublic: !And
    - !Condition AZ3Enabled
    - !Condition IsPublic


#------------------------------------------------------------------------------
Resources:

#------------------------------------------------------------------------------
#  NACLs

#  Network ACL
  NACLAZ3:
    Type: AWS::EC2::NetworkAcl
    Properties:
      VpcId: !Ref VPC
#      Tags:

# Inbound NACL: Allow All
  NACLAZ3EntryInboundAll:
    Type: AWS::EC2::NetworkAclEntry
    Properties:
      CidrBlock: 0.0.0.0/0
      Protocol: '-1'
      RuleAction: allow
      RuleNumber: '100'
      NetworkAclId: !Ref NACLAZ3

# Outbound NACL: Allow All
  NACLAZ3EntryOutboundAll:
    Type: AWS::EC2::NetworkAclEntry
    Properties:
      CidrBlock: 0.0.0.0/0
      Egress: 'true'
      Protocol: '-1'
      RuleAction: allow
      RuleNumber: '100'
      NetworkAclId: !Ref NACLAZ3

#------------------------------------------------------------------------------
# Availability Zone 1

# ---------------------------
# NACL
  NACLAZ1:
    Type: AWS::EC2::NetworkAcl
    Properties:
      VpcId: !Ref VPC
      Tags:
        - Key: Name
          Value: !Sub '${AWS::StackName}-AZ1'

# Inbound NACL: Allow All
  NACLAZ1EntryInboundAll:
    Type: AWS::EC2::NetworkAclEntry
    Properties:
      CidrBlock: 0.0.0.0/0
      Protocol: '-1'
      RuleAction: allow
      RuleNumber: '100'
      NetworkAclId: !Ref NACLAZ1

# Outbound NACL: Allow All
  NACLAZ1EntryOutboundAll:
    Type: AWS::EC2::NetworkAclEntry
    Properties:
      CidrBlock: 0.0.0.0/0
      Egress: 'true'
      Protocol: '-1'
      RuleAction: allow
      RuleNumber: '100'
      NetworkAclId: !Ref NACLAZ1

# ---------------------------
  RouteTableAZ1:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref VPC
      Tags:
        - Key: Name
          Value: !Sub '${AWS::StackName}-AZ1'

  RouteDefaultGWAZ1:
    Type: AWS::EC2::Route
    Condition: IsPublic
    Properties:
      RouteTableId: !Ref RouteTableAZ1
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref InternetGateway

# ---------------------------
  SubnetAZ1:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref VPC
      CidrBlock: !Ref SubnetAZ1CIDR
      AvailabilityZone: !Select [ 0, !GetAZs '' ]
      Tags:
        - Key: 'Name'
          Value: !Sub '${AWS::StackName}-AZ1'

# Association: Route Table
  SubnetAZ1RouteTableAssociation:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref SubnetAZ1
      RouteTableId: !Ref RouteTableAZ1

# Association: NACL
  SubnetAZ1NACLAssociation:
    Type: AWS::EC2::SubnetNetworkAclAssociation
    Properties:
      SubnetId: !Ref SubnetAZ1
      NetworkAclId: !Ref NACLAZ1
#------------------------------------------------------------------------------
# Availability Zone 2

# ---------------------------
# NACL
  NACLAZ2:
    Type: AWS::EC2::NetworkAcl
    Condition: AZ2Enabled
    Properties:
      VpcId: !Ref VPC
      Tags:
        - Key: Name
          Value: !Sub '${AWS::StackName}-AZ2'

# Inbound NACL: Allow All
  NACLAZ2EntryInboundAll:
    Type: AWS::EC2::NetworkAclEntry
    Condition: AZ2Enabled
    Properties:
      CidrBlock: 0.0.0.0/0
      Protocol: '-1'
      RuleAction: allow
      RuleNumber: '100'
      NetworkAclId: !Ref NACLAZ2

# Outbound NACL: Allow All
  NACLAZ2EntryOutboundAll:
    Type: AWS::EC2::NetworkAclEntry
    Condition: AZ2Enabled
    Properties:
      CidrBlock: 0.0.0.0/0
      Egress: 'true'
      Protocol: '-1'
      RuleAction: allow
      RuleNumber: '100'
      NetworkAclId: !Ref NACLAZ2

# ---------------------------
  RouteTableAZ2:
    Type: AWS::EC2::RouteTable
    Condition: AZ2Enabled
    Properties:
      VpcId: !Ref VPC
      Tags:
        - Key: Name
          Value: !Sub '${AWS::StackName}-AZ2'

  RouteDefaultGWAZ2:
    Type: AWS::EC2::Route
    Condition: AZ2EnabledAndIsPublic
    Properties:
      RouteTableId: !Ref RouteTableAZ2
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref InternetGateway

# ---------------------------
  SubnetAZ2:
    Type: AWS::EC2::Subnet
    Condition: AZ2Enabled
    Properties:
      VpcId: !Ref VPC
      CidrBlock: !Ref SubnetAZ2CIDR
      AvailabilityZone: !Select [ 1, !GetAZs '' ]
      Tags:
        - Key: Name
          Value: !Sub '${AWS::StackName}-AZ2'


# Association: Route Table
  SubnetAZ2RouteTableAssociation:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Condition: AZ2Enabled
    Properties:
      SubnetId: !Ref SubnetAZ2
      RouteTableId: !Ref RouteTableAZ2

# Association: NACL
  SubnetAZ2NACLAssociation:
    Type: AWS::EC2::SubnetNetworkAclAssociation
    Condition: AZ2Enabled
    Properties:
      SubnetId: !Ref SubnetAZ2
      NetworkAclId: !Ref NACLAZ2

#------------------------------------------------------------------------------
# Availability Zone 3

# ---------------------------
# NACL
  NACLAZ3:
    Type: AWS::EC2::NetworkAcl
    Condition: AZ3Enabled
    Properties:
      VpcId: !Ref VPC
      Tags:
        - Key: Name
          Value: !Sub '${AWS::StackName}-AZ3'

# Inbound NACL: Allow All
  NACLAZ3EntryInboundAll:
    Type: AWS::EC2::NetworkAclEntry
    Condition: AZ3Enabled
    Properties:
      CidrBlock: 0.0.0.0/0
      Protocol: '-1'
      RuleAction: allow
      RuleNumber: '100'
      NetworkAclId: !Ref NACLAZ3

# Outbound NACL: Allow All
  NACLAZ3EntryOutboundAll:
    Type: AWS::EC2::NetworkAclEntry
    Condition: AZ3Enabled
    Properties:
      CidrBlock: 0.0.0.0/0
      Egress: 'true'
      Protocol: '-1'
      RuleAction: allow
      RuleNumber: '100'
      NetworkAclId: !Ref NACLAZ3

# ---------------------------
  RouteTableAZ3:
    Type: AWS::EC2::RouteTable
    Condition: AZ3Enabled
    Properties:
      VpcId: !Ref VPC
      Tags:
        - Key: Name
          Value: !Sub '${AWS::StackName}-AZ3'

  RouteDefaultGWAZ3:
    Type: AWS::EC2::Route
    Condition: AZ3EnabledAndIsPublic
    Properties:
      RouteTableId: !Ref RouteTableAZ3
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref InternetGateway

# ---------------------------
  SubnetAZ3:
    Type: AWS::EC2::Subnet
    Condition: AZ3Enabled
    Properties:
      VpcId: !Ref VPC
      CidrBlock: !Ref SubnetAZ3CIDR
      AvailabilityZone: !Select [ 2, !GetAZs '' ]
      Tags:
        - Key: Name
          Value: !Sub '${AWS::StackName}-AZ3'


# Association: Route Table
  SubnetAZ3RouteTableAssociation:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Condition: AZ3Enabled
    Properties:
      SubnetId: !Ref SubnetAZ3
      RouteTableId: !Ref RouteTableAZ3

# Association: NACL
  SubnetAZ3NACLAssociation:
    Type: AWS::EC2::SubnetNetworkAclAssociation
    Condition: AZ3Enabled
    Properties:
      SubnetId: !Ref SubnetAZ3
      NetworkAclId: !Ref NACLAZ3


#------------------------------------------------------------------------------
# Outputs
Outputs:
  SubnetList1:
    Value: !Sub '${SubnetAZ1}'
  SubnetList2:
    Condition: AZ2Enabled
    Value: !Sub '${SubnetAZ1},${SubnetAZ2}'
  SubnetList3:
    Condition: AZ3Enabled
    Value: !Sub '${SubnetAZ1},${SubnetAZ2},${SubnetAZ3}'
  SubnetIdAZ1:
    Value: !Sub '${SubnetAZ1}'
  SubnetIdAZ2:
    Condition: AZ2Enabled
    Value: !Sub '${SubnetAZ2}'
  SubnetIdAZ3:
    Condition: AZ3Enabled
    Value: !Sub '${SubnetAZ3}'
  RouteTableIdAZ1:
    Value: !Sub '${RouteTableAZ1}'
  RouteTableIdAZ2:
    Condition: AZ2Enabled
    Value: !Sub '${RouteTableAZ2}'
  RouteTableIdAZ3:
    Condition: AZ3Enabled
    Value: !Sub '${RouteTableAZ3}'
""")
        self.register_stack_output_config(segment_config_ref+'.az1.subnet_id', 'SubnetIdAZ1')
        if availability_zones > 1:
          self.register_stack_output_config(segment_config_ref+'.az2.subnet_id', 'SubnetIdAZ2')
        if availability_zones > 2:
          self.register_stack_output_config(segment_config_ref, '.az3.subnet_id', 'SubnetIdAZ3')

    def validate(self):
        #self.aim_ctx.log("Validating Segment Template")
        super().validate()

    def get_outputs_key_from_ref(self, aim_ref):
        ref_dict = self.aim_ctx.parse_ref(aim_ref)
        ref_parts = ref_dict['ref_parts']

        az_idx = len(ref_parts)-2
        resource_idx = az_idx + 1
        if ref_parts[resource_idx] == "subnet_id":
            return 'SubnetId' + ref_parts[az_idx].upper()
        elif ref_parts[resource_idx] == "route_table_id":
            return "RouteTableId" + ref_parts[az_idx].upper()
        return None