# RAG-S3Vector



### Testing
```shell
aws lambda invoke --function-name cits-rag-s3vector-query --cli-binary-format raw-in-base64-out --payload '{"query": "How is weather today?"}' --profile terraform response.json && cat response.json
aws bedrock list-foundation-models --profile terraform --query 'modelSummaries[?contains(modelId, 'embed')].modelId' --output table
```


