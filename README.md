# etcd-aws-cluster

This container was **VERY** inspired on [MonsantoCo/etcd-aws-cluster](https://github.com/MonsantoCo/etcd-aws-cluster) to assist in the creation of an etcd (2.x) cluster from an AWS auto scaling group.
 
The original container created the cluster based on the scaling group of the running machine, this version implements some extra features:

- It will get all scaling groups of the Cloud Formation stack and with a tag `CoreOSCluster` with value `Yes`;
- After the limit configured on `MAX_NUMBER_MEMBERS` the next machines will enter the cluster as proxy;
 
Please refer to the original repo for instructions on how to use it.
