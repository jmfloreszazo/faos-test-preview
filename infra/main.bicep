// Agent Optimizer example infrastructure.
// Subscription-scope deployment: creates the resource group and, inside it,
// the Foundry project, the model deployment, ACR, Log Analytics and App Insights.
targetScope = 'subscription'

@minLength(1)
@description('azd environment name (resource prefix).')
param environmentName string

@minLength(1)
@description('Deployment region. Use eastus2 for Agent Service / Agent Optimizer.')
param location string = 'eastus2'

@description('Name of the agent base model deployment.')
param modelDeploymentName string = 'gpt-4.1-mini'

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'resources'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
    modelDeploymentName: modelDeploymentName
  }
}

output AZURE_LOCATION string = location
output AZURE_AI_PROJECT_ENDPOINT string = resources.outputs.projectEndpoint
output AZURE_AI_PROJECT_ID string = resources.outputs.projectId
output AZURE_AI_MODEL_DEPLOYMENT_NAME string = modelDeploymentName
output APPLICATIONINSIGHTS_CONNECTION_STRING string = resources.outputs.appInsightsConnectionString
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.containerRegistryEndpoint
output AZURE_CONTAINER_REGISTRY_NAME string = resources.outputs.containerRegistryName
