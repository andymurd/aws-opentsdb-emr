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

## Create the EMR Cluster in Our New VPC

This command will create the EMR cluster of one master and two core workers, running HBase:

	aws cloudformation create-stack --region $AWS_REGION --stack-name opentsdb-emr-cluster --capabilities CAPABILITY_IAM --template-body file://./cloudformation/emr.yaml --parameters ParameterKey=SubnetID,ParameterValue=$PRIVATE_SUBNET_ID | tee results/emr_stack.json

Note that this stack creates a number of IAM resources (roles and instance profiles for the EC2 servers) so the extra ` --capabilities CAPABILITY_IAM` is necessary.

There are a number of parameters to this CloudFormation stack, allowing you to choose things like the EC2 instance types, logging buckets etc. You are strongly encouraged to read through the stack definition file.

Grab the stack name from the response:

	export EMR_STACK_ARN=`cat results/emr_stack.json | jq -r .StackId`


Extract the VPC ID:

	aws emr --region $AWS_REGION list-clusters --active | tee results/emr_cluster.json
	export EMR_CLUSTER_ID=`cat results/emr_cluster.json | jq -r .Clusters[0].Id`


Side note: If you want to delete this EMR cluster and associated EC2 instances, but note that the data remains in the S3 storage buckets: 

	aws cloudformation delete-stack --region $AWS_REGION --stack-name $EMR_STACK_ARN

