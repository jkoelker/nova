# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
#
#    Licensed under the Apache License, Version 2.0 (the 'License'); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an 'AS IS' BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import migrate as m
import sqlalchemy as sa

from nova import utils


meta = sa.MetaData()


def _get_table(name):
    return sa.Table(name, meta, autoload=True)


def upgrade(migrate_engine):
    meta.bind = migrate_engine

    instances = _get_table('instances')
    networks = _get_table('networks')
    vifs = _get_table('virtual_interfaces')
    fixed_ips = _get_table('fixed_ips')
    floating_ips = _get_table('floating_ips')

    floating_ips.create_column(sa.Column('uuid', sa.String(36)))
    fixed_ips.create_column(sa.Column('uuid', sa.String(36)))

    rows = migrate_engine.execute(fixed_ips.select())
    for row in rows:
        fixed_ip_uuid = str(utils.gen_uuid())
        migrate_engine.execute(fixed_ips.update()\
                .where(fixed_ips.c.id == row[0])\
                .values(uuid=fixed_ip_uuid))

    rows = migrate_engine.execute(floating_ips.select())
    for row in rows:
        floating_ip_uuid = str(utils.gen_uuid())
        migrate_engine.execute(floating_ips.update()\
                .where(floating_ips.c.id == row[0])\
                .values(uuid=floating_ip_uuid))

    floating_ips.create_column(sa.Column('fixed_ip_uuid', sa.String(36)))

    floating_ips_fixed_subquery = sa.select([fixed_ips.c.uuid])\
        .where(fixed_ips.c.id == floating_ips.c.fixed_ip_id)
    floating_ips.update()\
        .values(fixed_ip_uuid=floating_ips_fixed_subquery.as_scalar())\
        .execute()

    floating_ips.c.fixed_ip_id.drop()
    floating_ips.c.fixed_ip_uuid.alter(name='fixed_ip_id')

    fixed_ips.create_column(sa.Column('network_uuid', sa.String(36)))
    fixed_ips.create_column(sa.Column('virtual_interface_uuid',
                                      sa.String(36)))
    fixed_ips.create_column(sa.Column('instance_uuid', sa.String(36)))

    fixed_ips_network_subquery = sa.select([networks.c.uuid])\
        .where(networks.c.id == fixed_ips.c.network_id)
    fixed_ips_instance_subquery = sa.select([instances.c.uuid])\
        .where(instances.c.id == fixed_ips.c.instance_id)
    fixed_ips_vif_subquery = sa.select([vifs.c.uuid])\
        .where(vifs.c.id == fixed_ips.c.virtual_interface_id)

    fixed_ips.update()\
        .values(network_uuid=fixed_ips_network_subquery.as_scalar())\
        .execute()
    fixed_ips.update()\
        .values(instance_uuid=fixed_ips_instance_subquery.as_scalar())\
        .execute()
    fixed_ips.update()\
        .values(virtual_interface_uuid=fixed_ips_vif_subquery.as_scalar())\
        .execute()

    fixed_ips.c.network_id.drop()
    fixed_ips.c.instance_id.drop()
    fixed_ips.c.virtual_interface_id.drop()
    fixed_ips.c.network_uuid.alter(name='network_id')
    fixed_ips.c.virtual_interface_uuid.alter(name='virtual_interface_id')
    fixed_ips.c.instance_uuid.alter(name='instance_id')

    vifs.create_column(sa.Column('network_uuid', sa.String(36)))
    vifs.create_column(sa.Column('instance_uuid', sa.String(36)))

    vifs_network_subquery = sa.select([networks.c.uuid])\
        .where(networks.c.id == vifs.c.network_id)
    vifs_instance_subquery = sa.select([instances.c.uuid])\
        .where(instances.c.id == vifs.c.instance_id)

    vifs.update()\
        .values(network_uuid=vifs_network_subquery.as_scalar()).execute()
    vifs.update()\
        .values(instance_uuid=vifs_instance_subquery.as_scalar()).execute()

    vifs.c.network_id.drop()
    vifs.c.instance_id.drop()
    vifs.c.network_uuid.alter(name='network_id')
    vifs.c.instance_uuid.alter(name='instance_id')

    m.PrimaryKeyConstraint(networks.c.uuid).create()
    networks.c.id.drop()
    networks.c.uuid.alter(name='id')

    m.PrimaryKeyConstraint(vifs.c.uuid).create()
    vifs.c.id.drop()
    vifs.c.uuid.alter(name='id')

    m.PrimaryKeyConstraint(fixed_ips.c.uuid).create()
    fixed_ips.c.id.drop()
    fixed_ips.c.uuid.alter(name='id')

    m.PrimaryKeyConstraint(floating_ips.c.uuid).create()
    floating_ips.c.id.drop()
    floating_ips.c.uuid.alter(name='id')


def downgrade(migrate_engine):
    pass
