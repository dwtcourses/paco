import os
import troposphere
import troposphere.elasticache
from aim.cftemplates.cftemplates import CFTemplate
from aim.models.references import Reference
from io import StringIO
from enum import Enum
import base64
from aim.models import vocabulary, schemas


class ElastiCache(CFTemplate):
    """
    Creates an Amazon ElastiCache Redis replication group (AWS::ElastiCache::ReplicationGroup).
    A replication group is a collection of cache clusters, where one of the clusters is a
    primary read-write cluster and the others are read-only replicas.
    """
    def __init__(
        self,
        aim_ctx,
        account_ctx,
        aws_region,
        stack_group,
        stack_tags,
        app_id,
        grp_id,
        res_id,
        elasticache_config,
        config_ref=None
    ):
        super().__init__(
            aim_ctx,
            account_ctx,
            aws_region,
            enabled=elasticache_config.is_enabled(),
            config_ref=config_ref,
            stack_group=stack_group,
            stack_tags=stack_tags,
            change_protected=elasticache_config.change_protected
        )
        self.set_aws_name('ElastiCache', grp_id, res_id, elasticache_config.engine )

        if elasticache_config.is_enabled() == True:
            # Security Groups
            sg_params = []
            vpc_sg_list = []
            for sg_ref in elasticache_config.security_groups:
                ref = Reference(sg_ref)
                sg_param_name = 'SecurityGroupId'+ref.parts[-2]+ref.parts[-1]
                sg_param = self.create_cfn_parameter(
                    name=sg_param_name,
                    param_type='String',
                    description='VPC Security Group Id',
                    value=sg_ref + '.id',
                    use_troposphere=True
                )
                sg_params.append(sg_param)
                vpc_sg_list.append(troposphere.Ref(sg_param))

            # Subnet Ids
            subnet_ids_param = self.create_cfn_parameter(
                name='SubnetIdList',
                param_type='List<String>',
                description='List of Subnet Ids to provision ElastiCache nodes',
                value=elasticache_config.segment+'.subnet_id_list',
                use_troposphere=True
            )

            # ElastiCache Subnet Group
            subnet_group_dict = {
                'Description': troposphere.Ref('AWS::StackName'),
                'SubnetIds' : troposphere.Ref(subnet_ids_param)
            }
            subnet_group_res = troposphere.elasticache.SubnetGroup.from_dict(
                'SubnetGroup',
                subnet_group_dict
            )

            # ElastiCache Resource
            elasticache_dict = elasticache_config.cfn_export_dict
            elasticache_dict['SecurityGroupIds'] = vpc_sg_list
            elasticache_dict['CacheSubnetGroupName'] = troposphere.Ref(subnet_group_res)
            if elasticache_config.description:
                elasticache_dict['ReplicationGroupDescription'] = elasticache_config.description
            else:
                elasticache_dict['ReplicationGroupDescription'] = troposphere.Ref('AWS::StackName')

            cfn_cache_cluster_name = 'ReplicationGroup'
            cache_cluster_res = troposphere.elasticache.ReplicationGroup.from_dict(
                cfn_cache_cluster_name,
                elasticache_dict
            )

        # Troposphere Template Generation
        self.init_template('ElastiCache: {} - {}'.format(
            elasticache_config.engine,
            elasticache_config.engine_version
        ))
        if elasticache_config.is_enabled() == True:
            for sg_param in sg_params:
                self.template.add_parameter(sg_param)
            self.template.add_parameter(subnet_ids_param)
            self.template.add_resource(subnet_group_res)
            self.template.add_resource(cache_cluster_res)
        else:
            # There is no way to stop a cluster, it must be removed.
            # Leave a dummy resource to allow the stack to delete
            # the resources.
            self.template.add_resource(
                troposphere.cloudformation.WaitConditionHandle(title="DummyResource")
            )

        self.set_template(self.template.to_yaml())
