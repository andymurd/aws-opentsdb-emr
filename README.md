# OpenTSDB on AWS Elastic Map-Reduce

This repo contains a recipe to help you get [OpenTSDB](http://opentsdb.net/) running on top of AWS infrastructure, specifically with its datastore handled by [AWS Elastic Map-Reduce](https://aws.amazon.com/emr/) (aka EMR).

The steps we'll be following are:
1. Create a VPC 
	- One public subnet but allowing only our IP ingres on port 80. This will host the OpenTSDB server
	- One private subnet for the EMR hosts
	- Access from the public to private for all ports needed
2. Set up a simple EMR cluster, running HBase
3. Bootstrap the creation of two HBase tables for OpenTSDB
4. Spin up an EC2 server for OpenTSDB and connect it our HBase service
5. Verify that the server is up and responding to HTTP requests
6. Upload a ton of data
7. Run some queries

You'll need:
- An AWS account with sufficient privileges to run AWS CloudFormation and create all the things listed above
- The [AWS CLI tools](https://aws.amazon.com/cli/) installed on your computer
- [jq](https://stedolan.github.io/jq/), the JSON processor for the command-line

## Preparation

Make sure that your `.aws/credentials` file is up to date and ready.

If you need to choose a profile or set access keys, then do so via environment variables:

	export AWS_PROFILE=my_profile

You should choose a region in the same manner, unless your `.aws/config` file does so already:

	export AWS_REGION=ap-southeast-2

## Create a Key Pair for SSH Access

If you already have a key pair configured in EC2, you can skip this step. Otherwise, use the AWS Console to [generate a new key pair and download it to your computer](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html).

For the rest of this tutorial, the key will be named `aws-opentsdb-emr`. Adjust as necessary to suit your set up.

## Create the VPC

This command will create the VPC and two subnets:

	aws cloudformation create-stack --region $AWS_REGION --stack-name opentsdb-emr-vpc --template-body file://./cloudformation/vpc.yaml --parameters ParameterKey=VPCName,ParameterValue=opentsdb_emr_vpc | tee results/vpc_stack.json

Grab the stack name from the response:

	export VPC_STACK_ARN=`cat results/vpc_stack.json | jq -r .StackId`

Extract the VPC ID:

	aws ec2 --region $AWS_REGION describe-vpcs --filters Name=tag:aws:cloudformation:stack-id,Values=$VPC_STACK_ARN | tee results/vpc.json
	export VPC_ID=`cat results/vpc.json | jq -r .Vpcs[0].VpcId`

Extract the two subnet IDs:

	aws ec2 --region $AWS_REGION describe-subnets --filter Name=vpc-id,Values=$VPC_ID --filter Name=tag:Network,Values=Private | tee results/private_subnet.json
	export PRIVATE_SUBNET_ID=`cat results/private_subnet.json | jq -r .Subnets[0].SubnetId`

	aws ec2 --region $AWS_REGION describe-subnets --filter Name=vpc-id,Values=$VPC_ID --filter Name=tag:Network,Values=Public | tee results/public_subnet.json
	export PUBLIC_SUBNET_ID=`cat results/public_subnet.json | jq -r .Subnets[0].SubnetId`

Side note: If you want to delete this VPC and subnets, 

	aws cloudformation delete-stack --region $AWS_REGION --stack-name $VPC_STACK_ARN

## Create the EMR Cluster in the Private Subnet of Our New VPC

This command will create the EMR cluster of one master and two core workers, running HBase:

	aws cloudformation create-stack --region $AWS_REGION --stack-name opentsdb-emr-cluster --capabilities CAPABILITY_IAM --template-body file://./cloudformation/emr.yaml --parameters ParameterKey=SubnetID,ParameterValue=$PRIVATE_SUBNET_ID ParameterKey=KeyName,ParameterValue=aws-opentsdb-emr | tee results/emr_stack.json

Note that this stack creates a number of IAM resources (roles and instance profiles for the EC2 servers) so the extra ` --capabilities CAPABILITY_IAM` is necessary.

There are a number of parameters to this CloudFormation stack, allowing you to choose things like the EC2 instance types, logging buckets etc. You are strongly encouraged to read through the stack definition file.

Grab the stack name from the response:

	export EMR_STACK_ARN=`cat results/emr_stack.json | jq -r .StackId`


Extract the Cluster ID:

	aws emr --region $AWS_REGION list-clusters --active | tee results/emr_cluster.json
	export EMR_CLUSTER_ID=`cat results/emr_cluster.json | jq -r .Clusters[0].Id`

Find the private IP of the master node in the cluster - ??? not sure how to do this via aws cli.

	export EMR_MASTER_IP=10.0.2.155

Side note: If you want to delete this EMR cluster and associated EC2 instances, but note that the data remains in the S3 storage buckets: 

*NB*: If you want to re-create this cluster and access your data later, you need to endure that the following gets run on the HBase Master server:
	/usr/lib/hbase/bin/disable_all_tables.sh

Then you can delete the CloudFormation stack like this:

	aws cloudformation delete-stack --region $AWS_REGION --stack-name $EMR_STACK_ARN

## Run a Server and Install OpenTSDB in the Public Subnet of Our New VPC

This command will create a single EC2 instanace in the public subnet, running OpenTSDB and using HBase on our EMR cluster for storage:

	aws cloudformation create-stack --region $AWS_REGION --stack-name opentsdb-emr-opentsdb --template-body file://./cloudformation/opentsdb.yaml --parameters ParameterKey=SubnetID,ParameterValue=$PUBLIC_SUBNET_ID ParameterKey=HBaseMasterIP,ParameterValue=$EMR_MASTER_IP ParameterKey=ZookeeperIP,ParameterValue=$EMR_MASTER_IP ParameterKey=KeyName,ParameterValue=aws-opentsdb-emr ParameterKey=VpcID,ParameterValue=$VPC_ID ParameterKey=InstanceName,ParameterValue=opentsdb-1 | tee results/opentsdb_stack.json

There are a number of parameters to this CloudFormation stack, allowing you to choose things like the EC2 instance types, logging buckets etc. You are strongly encouraged to read through the stack definition file.

Grab the stack name from the response:

	export OPENTSDB_STACK_ARN=`cat results/opentsdb_stack.json | jq -r .StackId`

Side note: If you want to delete this EMR cluster and associated EC2 instances, but note that the data remains in the S3 storage buckets: 

	aws cloudformation delete-stack --region $AWS_REGION --stack-name $OPENTSDB_STACK_ARN

Manually update the AWS security groups to allow ingress from your OpenTSDB server on these ports:

	16000-16999
	22

## Install and Configure OpenTSDB

It gets quite manual from here in...

The first step is to login to the AWS console, choose `EC2 -> Security Groups -> Inbound` and give your IP access to all (0-65535 incoming TVP/IP ports).

Now you need to initiate ssh forwarding:

	`ssh-agent`
	ssh-add aws-opentsdb-emr
	ssh -A <OPEN_TSDB_PUBLIC_IP>

Now you have ssh'd to your new OpenTSDB EC2 instance, run the following:

	echo "\n$EMR_MASTER_IP\tzookeeper-server\n$EMR_MASTER_IP\tzookeeper-server\n" >> /etc/hosts
    yum install nc
    echo ruok | nc -w 5 zookeeper-server 2181
    
    wget https://github.com/OpenTSDB/opentsdb/releases/download/v2.4.0/opentsdb-2.4.0.noarch.rpm
    yum install https://github.com/OpenTSDB/opentsdb/releases/download/v2.4.0/opentsdb-2.4.0.noarch.rpm

Copy the create script and hop across to the EMR master:

	scp /usr/share/opentsdb/tools/create_table.sh hadoop@zookeeper-server:/home/hadoop/
	ssh zookeeper-server

Create the tables (you only need to do this once):

	COMPRESSION=LZO HBASE_HOME=/usr ./create_table.sh

Create each new metric name. You'll need to do this for every metric that you want:

	tsdb mkmetric my.metric.name


## Access the OpenTSDB User Interface

If everything went well, you should be able to point your browser at `http://<OPEN_TSDB_PUBLIC_IP>:4242` to access the API.

For troubleshooting, try reading the logs on the OpenTSDB server:

	/var/log/opentsdb/opentsdb-ip-XXXXXX.ap-southeast-2.compute.internal-opentsdb.*

To dive deeper, ssh from the OpenTSDB server to your EMR master (you'll need to use a different username):

	ssh hadoop@zookeeper-server

Once there, look for the Hadoop and HBase logs:

	/var/log/zookeeper/
	/var/log/hbase/
	/var/log/hadoop-hdfs/
	
