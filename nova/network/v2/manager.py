# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2012 Openstack, LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from nova import exception
from nova import flags
from nova import manager
from nova import log as logging
from nova import utils


FLAGS = flags.FLAGS
LOG = logging.getLogger('nova.network')


class NetworkManager(manager.Manager):
    """Network Manager"""
    def __init__(self, network_driver=FLAGS.network_driver,
                 ipam_driver=FLAGS.ipam_driver, dns_driver=FLAGS.dns_driver,
                 *args, **kwargs):
        self.ipam_driver = utils.import_class(ipam_driver)()
        self.network_driver = utils.import_class(network_driver)()
        self.dns_driver = utils.import_class(dns_driver)()

        super(NetworkManager, self).__init__(*args, **kwargs)

    def get_all_networks(self, context):
        pass

    def get_network(self, context, network_uuid):
        pass

    def delete_network(self, context, network_uuid):
        pass

    def disassociate(self, context, network_uuid):
        pass

    def get_fixed_ip(self, context, id):
        pass

    def get_floating_ip(self, context, id):
        pass

    def get_floating_ip_pools(self, context):
        pass

    def get_floating_ip_by_address(self, context, address):
        pass

    def get_floating_ips_by_project(self, context):
        pass

    def get_floating_ips_by_fixed_address(self, context, fixed_address):
        pass

    def get_vifs_by_instance(self, context, instance_id):
        pass

    def allocate_floating_ip(self, context, pool=None):
        pass

    def release_floating_ip(self, context, address,
                            affect_auto_assigned=False):
        pass

    def associate_floating_ip(self, context, floating_address,
                             fixed_address, affect_auto_assigned=False):
        pass

    def disassociate_floating_ip(self, context, address,
                                 affect_auto_assigned=False):
        pass

    def allocate_for_instance(self, context, instance_id, instance_uuid,
                              project_id, host, instance_type_id):
        pass

    def deallocate_for_instance(self, context, instance_id, project_id):
        pass

    def add_fixed_ip_to_instance(self, context, instance_id, host,
                                 network_id):
        pass

    def remove_fixed_ip_from_instance(self, context, instance_id, address):
        pass

    def add_network_to_project(self, context, project_id):
        pass

    def get_instance_nw_info(self, context, instance_id, instance_uuid,
                             instance_type_id, host):
        pass

    def validate_networks(self, context, requested_networks):
        pass

    def get_instance_uuids_by_ip_filter(self, context, filters):
        pass

    def get_dns_zones(self, context):
        pass

    def add_dns_entry(self, context, address, name, dns_type, zone):
        pass

    def modify_dns_entry(self, context, name, address, dns_zone):
        pass

    def delete_dns_entry(self, context, name, zone):
        pass

    def get_dns_entries_by_address(self, context, address, zone):
        pass

    def get_dns_entries_by_name(self, context, name, zone):
        pass
