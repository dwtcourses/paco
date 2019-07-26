from aim.stack_group import StackEnum, StackOrder, Stack, StackGroup, StackTags
from aim import models
from aim.models import schemas
from pprint import pprint
import aim.cftemplates

class NetworkStackGroup(StackGroup):
    def __init__(self, aim_ctx, account_ctx, subenv_ctx, stack_tags):

        super().__init__(aim_ctx,
                         account_ctx,
                         subenv_ctx.netenv_id,
                         "Net",
                         subenv_ctx)

        self.subenv_ctx = subenv_ctx
        self.config_ref_prefix = self.subenv_ctx.config_ref_prefix
        self.region = self.subenv_ctx.region
        self.stack_tags = stack_tags

    def init(self):
        # Network Stack Templates
        print("NetworkStackGroup Init: VPC")
        # VPC Stack
        vpc_config = self.subenv_ctx.vpc_config()
        vpc_config_ref = '.'.join([self.config_ref_prefix, "network.vpc"])
        vpc_template = aim.cftemplates.VPC(self.aim_ctx,
                                           self.account_ctx,
                                           self.region,
                                           vpc_config,
                                           vpc_config_ref)
        self.vpc_stack = Stack(aim_ctx=self.aim_ctx,
                               account_ctx=self.account_ctx,
                               grp_ctx=self,
                               stack_config=vpc_config,
                               template=vpc_template,
                               aws_region=self.region,
                               stack_tags=StackTags(self.stack_tags))

        self.add_stack_order(self.vpc_stack)

        # Segments
        print("NetworkStackGroup Init: Segments")
        #print("Segments -----------")
        self.segment_list = []
        self.segment_dict = {}
        for segment_id in self.subenv_ctx.segment_ids():
            segment_config = self.subenv_ctx.segment_config(segment_id)
            segment_config.resolve_ref_obj = self
            segment_config_ref = '.'.join([self.config_ref_prefix, "network.vpc.segments", segment_id])
            segment_template = aim.cftemplates.Segment(self.aim_ctx,
                                                       self.account_ctx,
                                                       self.region,
                                                       self.subenv_ctx,
                                                       segment_id,
                                                       segment_config,
                                                       segment_config_ref)
            segment_stack = Stack(self.aim_ctx,
                                  self.account_ctx,
                                  self,
                                  segment_config,
                                  segment_template,
                                  aws_region=self.region,
                                  stack_tags=StackTags(self.stack_tags))
            self.segment_dict[segment_id] = segment_stack
            self.segment_list.append(segment_stack)
            self.add_stack_order(segment_stack, [StackOrder.PROVISION])

        # Security Groups
        print("NetworkStackGroup Init: Security Groups")
        #print("Security Groups -----------")
        #pprint(self.netenv_config.config_dict)
        sg_config = self.subenv_ctx.security_groups()
        self.sg_list = []
        self.sg_dict = {}
        for sg_id in sg_config:
            # Set resolve_ref_obj
            for sg_obj_id in sg_config[sg_id]:
                sg_config[sg_id][sg_obj_id].resolve_ref_obj = self
            sg_group_config_ref = '.'.join([self.config_ref_prefix, "network.vpc.security_groups", sg_id])
            sg_template = aim.cftemplates.SecurityGroups( aim_ctx=self.aim_ctx,
                                                          account_ctx=self.account_ctx,
                                                          aws_region=self.region,
                                                          subenv_ctx=self.subenv_ctx,
                                                          security_groups_config=sg_config[sg_id],
                                                          sg_group_id=sg_id,
                                                          sg_group_config_ref=sg_group_config_ref )
            sg_stack = Stack(self.aim_ctx,
                             self.account_ctx,
                             self,
                             None, #self.netenv_config,
                             sg_template,
                             aws_region=self.region,
                             stack_tags=StackTags(self.stack_tags))
            self.sg_list.append(sg_stack)
            self.add_stack_order(sg_stack, [StackOrder.PROVISION])
            self.sg_dict[sg_id] = sg_stack

        # Wait for Segment Stacks
        for segment_stack in self.segment_list:
            self.add_stack_order(segment_stack, [StackOrder.WAIT])

        # NAT Gateway
        self.nat_list = []
        for nat_id in self.subenv_ctx.nat_gateway_ids():
            # We now disable the NAT Gatewy in the template sot hat we can delete it and recreate
            # it when disabled.
            #if self.subenv_ctx.nat_gateway_enabled(nat_id) == False:
            #    print("NetworkStackGroup Init: NAT Gateway: %s *disabled*" % (nat_id))
            #    continue
            print("NetworkStackGroup Init: NAT Gateway: %s" % (nat_id))
            nat_config_ref = '.'.join([self.config_ref_prefix, "network.vpc.nat_gateway", nat_id])
            nat_template = aim.cftemplates.NATGateway( aim_ctx=self.aim_ctx,
                                                       account_ctx=self.account_ctx,
                                                       aws_region=self.region,
                                                       subenv_ctx=self.subenv_ctx,
                                                       nat_id=nat_id,
                                                       config_ref=nat_config_ref)
            nat_stack = Stack(self.aim_ctx,
                              self.account_ctx,
                              self,
                              None, #self.netenv_config,
                              nat_template,
                              aws_region=self.region,
                              stack_tags=StackTags(self.stack_tags))
            self.nat_list.append(nat_stack)
            self.add_stack_order(nat_stack, [StackOrder.PROVISION])

        for nat_stack in self.nat_list:
            self.add_stack_order(nat_stack, [StackOrder.WAIT])

        for sg_stack in self.sg_list:
            # Wait for Securtiy Group Stacks
            self.add_stack_order(sg_stack, [StackOrder.WAIT])

        print("NetworkStackGroup Init: Completed")

    def get_vpc_stack(self):
        return self.vpc_stack

    def get_segment_stack(self, segment_id):
        for segment_stack in self.segment_list:
            if segment_stack.template.config_ref.endswith(segment_id):
                return segment_stack
        raise StackException(AimErrorCode.Unknown)

    def get_security_group_stack(self, sg_id):
        return self.sg_dict[sg_id]

    def get_segment_stack(self, segment_id):
        return self.segment_dict[segment_id]

    def resolve_ref(self, ref):
        if ref.raw.find('network.vpc.segments') != -1:
            segment_id = ref.next_part('network.vpc.segments')
            return self.get_segment_stack(segment_id)
        if schemas.ISecurityGroup.providedBy(ref.resource):
            if ref.resource_ref == 'id':
                sg_id = ref.parts[-3]
                return self.get_security_group_stack(sg_id)


    def validate(self):
        # Generate Stacks
        # VPC Stack
        super().validate()

    def provision(self):
        # self.validate()
        super().provision()
