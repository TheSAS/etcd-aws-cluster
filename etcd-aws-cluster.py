import requests
import json
import sys
import os
import boto.ec2
import boto.ec2.autoscale

# ETCD API https://coreos.com/etcd/docs/2.0.11/other_apis.html
STATUS_ADD_OK = 201
STATUS_ALREADY_ADDED = 409
STATUS_DELETE_OK = 204

MAX_NUMBER_MEMBERS = 9
ETCD_PEERS_FILE_PATH = '/etc/sysconfig/etcd-peers'

# If the script has already run just exit
if os.path.isfile(ETCD_PEERS_FILE_PATH):
    print('etcd-peers file already created')
    sys.exit(0)

try:
    my_instance_data = requests.get('http://169.254.169.254/latest/dynamic/instance-identity/document').json()
    if not my_instance_data:
        print('Failed to get instance')
        sys.exit(1)
except Exception as e:
    print('Failed to get instance, message: {0}'.format(e))
    sys.exit(1)

ec2_connection = boto.ec2.connect_to_region(my_instance_data['region'])
my_instance = ec2_connection.get_all_instances(instance_ids=my_instance_data['instanceId'])[0].instances[0]
stack_name = my_instance.tags['aws:cloudformation:stack-name']
if not stack_name:
    print('It\'s not part of a cloudformation stack')
    sys.exit(0)

all_instances = []
autoscaling_connection = boto.ec2.autoscale.connect_to_region(my_instance_data['region'])
for scale_group in autoscaling_connection.get_all_groups():
    if not [tag for tag in scale_group.tags if tag.key == 'aws:cloudformation:stack-name' and tag.value == stack_name]:
        continue
    if not [tag for tag in scale_group.tags if tag.key == 'CoreOSCluster' and tag.value == 'Yes']:
        continue
    all_instances.extend(scale_group.instances)

all_instances = ec2_connection.get_all_instances(instance_ids=[instance.instance_id for instance in all_instances])
all_instances = [reservation.instances[0] for reservation in all_instances if reservation.instances[0].id != my_instance.id]
if not all_instances:
    print('Unable to find members of auto scaling group')
    sys.exit(1)

print('All instances but me: {0}'.format(', '.join([instance.private_ip_address for instance in all_instances])))

etcd_good_member_instance = None
etcd_members = None

for instance in all_instances:
    try:
        etcd_members = requests.get('http://{0}:2379/v2/members/'.format(instance.private_ip_address)).json()
        etcd_good_member_instance = instance
        print('Good member: {0}'.format(etcd_good_member_instance.private_ip_address))
        break
    except:
        pass

# If I am already listed as a member of the cluster assume that this is a new cluster
if etcd_members and etcd_members['members'] and not [member for member in etcd_members['members'] if member['name'] == my_instance.id]:
    print('Joining existing cluster')

    for member in etcd_members['members']:
        if not [instance for instance in all_instances if instance.id == member['name']]:
            print('Removing bad peer {0}'.format(instance.private_ip_address))
            try:
                response = requests.delete('http://{0}:2379/v2/members/{1}'.format(etcd_good_member_instance.private_ip_address, member['id']))
                if response.status_code != STATUS_DELETE_OK:
                    print('ERROR: Failed to remove peer {0}, return code {1}'.format(member['peerURLs'], response.status_code))
                    sys.exit(7)
            except Exception as e:
                print('ERROR: Failed to remove peer {0}, message: {1}'.format(member['peerURLs'], e))
                sys.exit(7)

    try:
        etcd_members = requests.get('http://{0}:2379/v2/members/'.format(etcd_good_member_instance.private_ip_address)).json()
    except Exception as e:
        print('ERROR: Failed to get the new members on {0}, message: {1}'.format(etcd_good_member_instance.private_ip_address, e))
        sys.exit(7)

    is_proxy = False
    if len(etcd_members['members']) < MAX_NUMBER_MEMBERS:
        print('Cluster is not full yet, adding new member')
        payload = {'peerURLs': ['http://{0}:2380'.format(my_instance.private_ip_address)], 'name': my_instance.id}
        response = requests.post('http://{0}:2379/v2/members'.format(etcd_good_member_instance.private_ip_address), data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        if response.status_code != STATUS_ALREADY_ADDED and response.status_code != STATUS_ADD_OK:
            print('ERROR: Failed to add peer {0}, return code {1}'.format(my_instance.private_ip_address, response.status_code))
            sys.exit(8)
    else:
        print('Adding as proxy')
        is_proxy = True

    initial_cluster = ''
    for member in etcd_members['members']:
        initial_cluster += '{0}={1},'.format(member['id'], member['peerURLs'][0])
    initial_cluster += '{0}=http://{1}:2380'.format(my_instance.id, my_instance.private_ip_address)

    print('Initial cluster: {0}'.format(initial_cluster))

    with open(ETCD_PEERS_FILE_PATH, 'w') as f:
        f.write('ETCD_INITIAL_CLUSTER_STATE=existing\n')
        f.write('ETCD_NAME={0}\n'.format(my_instance.id))
        f.write('ETCD_INITIAL_CLUSTER={0}\n'.format(initial_cluster))
        if is_proxy:
            f.write('ETCD_PROXY=on\n')
        f.close()

else:
    print('Joining new cluster')

    initial_cluster = ''
    for instance in all_instances:
        initial_cluster += '{0}=http://{1}:2380,'.format(instance.id, instance.private_ip_address)
    initial_cluster += '{0}=http://{1}:2380'.format(my_instance.id, my_instance.private_ip_address)

    print('Initial cluster: {0}'.format(initial_cluster))

    with open(ETCD_PEERS_FILE_PATH, 'w') as f:
        f.write('ETCD_INITIAL_CLUSTER_STATE=new\n')
        f.write('ETCD_NAME={0}\n'.format(my_instance.id))
        f.write('ETCD_INITIAL_CLUSTER={0}\n'.format(initial_cluster))
        f.close()

sys.exit(0)
