from paco import cftemplates
from paco.application.res_engine import ResourceEngine


class DashboardResourceEngine(ResourceEngine):
    def init_resource(self):
        self.stack_group.add_new_stack(
            self.aws_region,
            self.resource,
            cftemplates.CloudWatchDashboard,
            stack_tags=self.stack_tags,
        )
