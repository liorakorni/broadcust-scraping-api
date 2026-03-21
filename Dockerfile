FROM public.ecr.aws/lambda/python:3.10-arm64

COPY handler.py ${LAMBDA_TASK_ROOT}
COPY conf.py ${LAMBDA_TASK_ROOT}

CMD [ "handler.perplexity_search" ]
