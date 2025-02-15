# LocalStack Resource Provider Scaffolding v2
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, TypedDict

import localstack.services.cloudformation.provider_utils as util
from localstack.services.cloudformation.resource_provider import (
    OperationStatus,
    ProgressEvent,
    ResourceProvider,
    ResourceRequest,
)


class SQSQueueProperties(TypedDict):
    Arn: Optional[str]
    ContentBasedDeduplication: Optional[bool]
    DeduplicationScope: Optional[str]
    DelaySeconds: Optional[int]
    FifoQueue: Optional[bool]
    FifoThroughputLimit: Optional[str]
    KmsDataKeyReusePeriodSeconds: Optional[int]
    KmsMasterKeyId: Optional[str]
    MaximumMessageSize: Optional[int]
    MessageRetentionPeriod: Optional[int]
    QueueName: Optional[str]
    QueueUrl: Optional[str]
    ReceiveMessageWaitTimeSeconds: Optional[int]
    RedriveAllowPolicy: Optional[dict | str]
    RedrivePolicy: Optional[dict | str]
    SqsManagedSseEnabled: Optional[bool]
    Tags: Optional[list[Tag]]
    VisibilityTimeout: Optional[int]


class Tag(TypedDict):
    Key: Optional[str]
    Value: Optional[str]


REPEATED_INVOCATION = "repeated_invocation"

_queue_attribute_list = [
    "ContentBasedDeduplication",
    "DeduplicationScope",
    "DelaySeconds",
    "FifoQueue",
    "FifoThroughputLimit",
    "KmsDataKeyReusePeriodSeconds",
    "KmsMasterKeyId",
    "MaximumMessageSize",
    "MessageRetentionPeriod",
    "ReceiveMessageWaitTimeSeconds",
    "RedriveAllowPolicy",
    "RedrivePolicy",
    "SqsManagedSseEnabled",
    "VisibilityTimeout",
]


class SQSQueueProvider(ResourceProvider[SQSQueueProperties]):
    TYPE = "AWS::SQS::Queue"  # Autogenerated. Don't change
    SCHEMA = util.get_schema_path(Path(__file__))  # Autogenerated. Don't change

    def create(
        self,
        request: ResourceRequest[SQSQueueProperties],
    ) -> ProgressEvent[SQSQueueProperties]:
        """
        Create a new resource.

        Primary identifier fields:
          - /properties/QueueUrl



        Create-only properties:
          - /properties/FifoQueue
          - /properties/QueueName

        Read-only properties:
          - /properties/QueueUrl
          - /properties/Arn

        IAM permissions required:
          - sqs:CreateQueue
          - sqs:GetQueueUrl
          - sqs:GetQueueAttributes
          - sqs:ListQueueTags
          - sqs:TagQueue

        """
        # TODO: validations
        model = request.desired_state
        sqs = request.aws_client_factory.sqs

        if model.get("FifoQueue", False):
            model["FifoQueue"] = model["FifoQueue"]

        queue_name = model.get("QueueName")
        if not queue_name:
            # TODO: verify patterns here
            if model.get("FifoQueue"):
                queue_name = util.generate_default_name(
                    request.stack_name, request.logical_resource_id
                )[:-5]
                queue_name = f"{queue_name}.fifo"
            else:
                queue_name = util.generate_default_name(
                    request.stack_name, request.logical_resource_id
                )
            model["QueueName"] = queue_name

        attributes = self._compile_sqs_queue_attributes(model)
        result = request.aws_client_factory.sqs.create_queue(
            QueueName=model["QueueName"],
            Attributes=attributes,
            tags={t["Key"]: t["Value"] for t in model.get("Tags", [])},
        )

        # set read-only properties
        model["QueueUrl"] = result["QueueUrl"]
        model["Arn"] = sqs.get_queue_attributes(
            QueueUrl=result["QueueUrl"], AttributeNames=["QueueArn"]
        )["Attributes"]["QueueArn"]

        return ProgressEvent(
            status=OperationStatus.SUCCESS,
            resource_model=model,
            custom_context=request.custom_context,
        )

    def read(
        self,
        request: ResourceRequest[SQSQueueProperties],
    ) -> ProgressEvent[SQSQueueProperties]:
        """
        Fetch resource information

        IAM permissions required:
          - sqs:GetQueueAttributes
          - sqs:ListQueueTags
        """
        raise NotImplementedError

    def delete(
        self,
        request: ResourceRequest[SQSQueueProperties],
    ) -> ProgressEvent[SQSQueueProperties]:
        """
        Delete a resource

        IAM permissions required:
          - sqs:DeleteQueue
          - sqs:GetQueueAttributes
        """
        sqs = request.aws_client_factory.sqs
        try:
            queue_url = sqs.get_queue_url(QueueName=request.previous_state["QueueName"])["QueueUrl"]
            sqs.delete_queue(QueueUrl=queue_url)

        except sqs.exceptions.QueueDoesNotExist:
            return ProgressEvent(
                status=OperationStatus.SUCCESS, resource_model=request.desired_state
            )

        return ProgressEvent(status=OperationStatus.SUCCESS, resource_model=request.desired_state)

    def update(
        self,
        request: ResourceRequest[SQSQueueProperties],
    ) -> ProgressEvent[SQSQueueProperties]:
        """
        Update a resource

        IAM permissions required:
          - sqs:SetQueueAttributes
          - sqs:GetQueueAttributes
          - sqs:ListQueueTags
          - sqs:TagQueue
          - sqs:UntagQueue
        """
        sqs = request.aws_client_factory.sqs
        model = request.desired_state

        assert request.previous_state is not None

        should_replace = (
            request.desired_state.get("QueueName", request.previous_state["QueueName"])
            != request.previous_state["QueueName"]
        ) or (
            request.desired_state.get("FifoQueue", request.previous_state.get("FifoQueue"))
            != request.previous_state.get("FifoQueue")
        )

        if not should_replace:
            return ProgressEvent(OperationStatus.SUCCESS, resource_model=request.previous_state)

        # TODO: copied from the create handler, extract?
        if model.get("FifoQueue"):
            queue_name = util.generate_default_name(
                request.stack_name, request.logical_resource_id
            )[:-5]
            queue_name = f"{queue_name}.fifo"
        else:
            queue_name = util.generate_default_name(request.stack_name, request.logical_resource_id)

        # replacement (TODO: find out if we should handle this in the provider or outside of it)
        # delete old queue
        sqs.delete_queue(QueueUrl=request.previous_state["QueueUrl"])
        # create new queue (TODO: re-use create logic to make this more robust, e.g. for
        #  auto-generated queue names)
        model["QueueUrl"] = sqs.create_queue(QueueName=queue_name)["QueueUrl"]
        model["Arn"] = sqs.get_queue_attributes(
            QueueUrl=model["QueueUrl"], AttributeNames=["QueueArn"]
        )["Attributes"]["QueueArn"]
        return ProgressEvent(OperationStatus.SUCCESS, resource_model=model)

    def _compile_sqs_queue_attributes(self, properties: SQSQueueProperties) -> dict[str, str]:
        """
        SQS is really awkward in how the ``CreateQueue`` operation expects arguments. Most of a Queue's
        attributes are passed as a string values in the "Attributes" dictionary. So we need to compile this
        dictionary here.

        :param properties: the properties passed from cloudformation
        :return: a mapping used for the ``Attributes`` argument of the `CreateQueue` call.
        """
        result = {}

        for k in _queue_attribute_list:
            v = properties.get(k)

            if v is None:
                continue
            elif isinstance(v, str):
                pass
            elif isinstance(v, bool):
                v = str(v).lower()
            elif isinstance(v, dict):
                # RedrivePolicy and RedriveAllowPolicy
                v = json.dumps(v)
            elif isinstance(v, int):
                v = str(v)
            else:
                raise TypeError(f"cannot convert attribute {k}, unhandled type {type(v)}")

            result[k] = v

        return result

    def list(
        self,
        request: ResourceRequest[SQSQueueProperties],
    ) -> ProgressEvent[SQSQueueProperties]:
        resources = request.aws_client_factory.sqs.list_queues()
        return ProgressEvent(
            status=OperationStatus.SUCCESS,
            resource_models=[
                SQSQueueProperties(QueueUrl=url) for url in resources.get("QueueUrls", [])
            ],
        )
