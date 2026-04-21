param(
  [string]$Tag = "latest",
  [string]$DeployEnvFile = (Join-Path $PSScriptRoot ".deploy-worker.env")
)

$ErrorActionPreference = 'Stop'

$AwsRegion = $env:AWS_REGION
if ([string]::IsNullOrWhiteSpace($AwsRegion)) { $AwsRegion = 'ap-southeast-1' }

$AwsAccountId = $env:AWS_ACCOUNT_ID
$EcrRepository = $env:ECR_REPOSITORY
if ([string]::IsNullOrWhiteSpace($EcrRepository)) { $EcrRepository = 'oade-nsga2-sls-worker' }

$StackName = $env:STACK_NAME
if ([string]::IsNullOrWhiteSpace($StackName)) { $StackName = 'oade-nsga2-sls-worker-fargate' }

$TemplateFile = $env:TEMPLATE_FILE
if ([string]::IsNullOrWhiteSpace($TemplateFile)) { $TemplateFile = 'deploy/ecs-fargate/worker-fargate-stack.yaml' }

$VpcId = $env:VPC_ID
$SubnetIds = $env:SUBNET_IDS
$QueueArn = $env:QUEUE_ARN
$TableName = $env:TABLE_NAME
$BucketName = $env:BUCKET_NAME

$Cpu = $env:CPU
if ([string]::IsNullOrWhiteSpace($Cpu)) { $Cpu = '2048' }

$Memory = $env:MEMORY
if ([string]::IsNullOrWhiteSpace($Memory)) { $Memory = '4096' }

$AssignPublicIp = $env:ASSIGN_PUBLIC_IP
if ([string]::IsNullOrWhiteSpace($AssignPublicIp)) { $AssignPublicIp = 'DISABLED' }

function Write-Step([string]$Message) { Write-Host "[STEP] $Message" }
function Write-Info([string]$Message) { Write-Host "[INFO] $Message" }
function Write-Success([string]$Message) { Write-Host "[OK] $Message" }
function Write-ErrorLine([string]$Message) { Write-Host "[ERROR] $Message" -ForegroundColor Red }

function Load-EnvFile([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) { return }

  Get-Content -LiteralPath $Path | ForEach-Object {
    $line = $_.Trim()
    if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith('#')) { return }

    $separatorIndex = $line.IndexOf('=')
    if ($separatorIndex -lt 1) { return }

    $name = $line.Substring(0, $separatorIndex).Trim()
    $value = $line.Substring($separatorIndex + 1).Trim()

    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }

    [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
  }
}

function Resolve-AwsCli {
  $awsCommand = Get-Command aws -ErrorAction SilentlyContinue
  if ($null -ne $awsCommand) { return $awsCommand.Source }

  $awsExeCommand = Get-Command aws.exe -ErrorAction SilentlyContinue
  if ($null -ne $awsExeCommand) { return $awsExeCommand.Source }

  return $null
}

function Test-AwsCredentials([string]$AwsCli, [string]$Region) {
  $output = & $AwsCli sts get-caller-identity --region $Region 2>&1
  if ($LASTEXITCODE -eq 0) { return }

  $outputText = $output | Out-String
  if ($outputText -match 'NoCredentials' -or $outputText -match 'Unable to locate credentials') {
    Write-ErrorLine 'AWS credentials were not found in this shell.'
    Write-ErrorLine 'If you are using PowerShell, run aws configure / aws sso login in the same PowerShell session.'
    throw 'Missing AWS credentials'
  }

  Write-Host $outputText
  throw 'AWS CLI could not verify credentials'
}

function Test-AwsAccountMatch([string]$AwsCli, [string]$Region, [string]$ExpectedAccountId) {
  $callerAccount = (& $AwsCli sts get-caller-identity --query Account --output text --region $Region 2>$null).Trim()
  if ([string]::IsNullOrWhiteSpace($callerAccount)) {
    throw 'Unable to resolve AWS caller account from current credentials'
  }

  if ($callerAccount -ne $ExpectedAccountId) {
    throw "Credential/account mismatch: current credentials are for account $callerAccount, but AWS_ACCOUNT_ID is $ExpectedAccountId"
  }
}

Set-Location $PSScriptRoot
Load-EnvFile -Path $DeployEnvFile

if ([string]::IsNullOrWhiteSpace($AwsAccountId)) { $AwsAccountId = $env:AWS_ACCOUNT_ID }
if ([string]::IsNullOrWhiteSpace($AwsRegion)) { $AwsRegion = 'ap-southeast-1' }
if ([string]::IsNullOrWhiteSpace($EcrRepository)) { $EcrRepository = 'oade-nsga2-sls-worker' }
if ([string]::IsNullOrWhiteSpace($StackName)) { $StackName = 'oade-nsga2-sls-worker-fargate' }
if ([string]::IsNullOrWhiteSpace($TemplateFile)) { $TemplateFile = 'deploy/ecs-fargate/worker-fargate-stack.yaml' }
if ([string]::IsNullOrWhiteSpace($Cpu)) { $Cpu = '2048' }
if ([string]::IsNullOrWhiteSpace($Memory)) { $Memory = '4096' }
if ([string]::IsNullOrWhiteSpace($AssignPublicIp)) { $AssignPublicIp = 'DISABLED' }

$ImageLocal = "${EcrRepository}:$Tag"
$ImageUri = "${AwsAccountId}.dkr.ecr.${AwsRegion}.amazonaws.com/${EcrRepository}:$Tag"

Write-Step "Starting worker deploy with tag: $Tag"
Write-Info "Repository root: $PSScriptRoot"
Write-Info "AWS Region: $AwsRegion"
Write-Info "ECR Image URI: $ImageUri"

if ([string]::IsNullOrWhiteSpace($AwsAccountId) -or [string]::IsNullOrWhiteSpace($VpcId) -or [string]::IsNullOrWhiteSpace($SubnetIds) -or [string]::IsNullOrWhiteSpace($QueueArn) -or [string]::IsNullOrWhiteSpace($TableName) -or [string]::IsNullOrWhiteSpace($BucketName)) {
  Write-ErrorLine 'Missing required environment variables: AWS_ACCOUNT_ID, VPC_ID, SUBNET_IDS, QUEUE_ARN, TABLE_NAME, BUCKET_NAME'
  Write-ErrorLine 'Create a .deploy-worker.env file in the repo root by copying .deploy-worker.env.example and filling in real AWS values, or set those variables in the current PowerShell session before running this script.'
  exit 1
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-ErrorLine 'Docker CLI is not installed or not available in PATH.'
  exit 1
}

$AwsCli = Resolve-AwsCli
if ([string]::IsNullOrWhiteSpace($AwsCli)) {
  Write-ErrorLine 'AWS CLI is not installed or not available in PATH.'
  exit 1
}

Write-Step 'Step 1/5: Building Docker image'
docker build -t $ImageLocal .
Write-Success "Built image $ImageLocal"

Write-Step 'Checking AWS credentials'
Test-AwsCredentials -AwsCli $AwsCli -Region $AwsRegion
Write-Success 'AWS credentials are available'

Write-Step 'Verifying deploy target account'
Test-AwsAccountMatch -AwsCli $AwsCli -Region $AwsRegion -ExpectedAccountId $AwsAccountId
Write-Success "AWS credentials match AWS_ACCOUNT_ID=$AwsAccountId"

Write-Step 'Step 2/5: Logging in to AWS ECR'
& $AwsCli ecr get-login-password --region $AwsRegion | docker login --username AWS --password-stdin "$AwsAccountId.dkr.ecr.$AwsRegion.amazonaws.com"
Write-Success 'Logged in to ECR'

Write-Step 'Step 3/5: Tagging Docker image for ECR'
docker tag $ImageLocal $ImageUri
Write-Success "Tagged image as $ImageUri"

Write-Step 'Step 4/5: Pushing image to ECR'
docker push $ImageUri
Write-Success 'Pushed image to ECR'

Write-Step 'Step 5/5: Deploying CloudFormation stack'
& $AwsCli cloudformation deploy `
  --stack-name $StackName `
  --template-file $TemplateFile `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides `
    VpcId=$VpcId `
    SubnetIds=$SubnetIds `
    QueueArn=$QueueArn `
    ImageUri=$ImageUri `
    TableName=$TableName `
    BucketName=$BucketName `
    Cpu=$Cpu `
    Memory=$Memory `
    AssignPublicIp=$AssignPublicIp

Write-Success 'CloudFormation stack updated successfully'
Write-Success "Worker deployment completed for tag $Tag"