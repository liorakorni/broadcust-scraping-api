#!/bin/bash

set -e

cd "$(dirname "$0")/.."

# This machine has no default AWS profile, and serverless plus the checks below
# both need credentials to resolve SSM and push the image to ECR.
export AWS_PROFILE=${AWS_PROFILE:-broadcust}
export AWS_REGION=${AWS_REGION:-us-east-1}

BRANCH=$(git rev-parse --abbrev-ref HEAD)
STAGE=${1:-dev}

# The deployed stack is stage 'dev' (functions are perplexity-search-api-dev-*),
# so 'main' maps to 'dev' here rather than to 'live' as in the sibling services.
if [[ "$BRANCH" != "main" ]]; then
  echo "Only the 'main' branch may be used for deployment."
  exit 1
elif [[ "$STAGE" != "dev" ]]; then
  echo "Deploy to '$STAGE' from 'main' branch not allowed — 'main' deploys to 'dev'."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running — the Lambda container image cannot be built."
  exit 1
fi

for PARAM in perplexity-api-key firecrawl-api-key serpapi-key; do
  if ! aws ssm get-parameter --name "/broadcust/scraping-api/${PARAM}" >/dev/null 2>&1; then
    echo "Missing SSM parameter /broadcust/scraping-api/${PARAM} — serverless cannot resolve the environment."
    exit 1
  fi
done

echo "Deploying stage '$STAGE' from branch '$BRANCH'..."
npx serverless deploy --stage "$STAGE"
