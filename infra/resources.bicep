// Example resources (deployed inside the resource group).
@description('Deployment region.')
param location string

@description('Unique token for naming resources.')
param resourceToken string

@description('Common tags.')
param tags object

@description('Base model deployment name.')
param modelDeploymentName string

// --- Observability ---------------------------------------------------------

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${resourceToken}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// --- Foundry (AI Services) + project ---------------------------------------

resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: 'aisvc-${resourceToken}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'aisvc-${resourceToken}'
    publicNetworkAccess: 'Enabled'
    allowProjectManagement: true
  }
}

resource aiProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: aiAccount
  name: 'proj-${resourceToken}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {}
}

// --- Azure Container Registry (hosted agent image) -------------------------
// Agent Optimizer only accepts agents deployed as a container image. azd builds
// the image from the Dockerfile and pushes it to this ACR; the agent service
// pulls it using the project/account managed identity.

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'acr${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'Standard' }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource acrPullProject 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: containerRegistry
  name: guid(containerRegistry.id, aiProject.id, 'AcrPull')
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: aiProject.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource acrPullAccount 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: containerRegistry
  name: guid(containerRegistry.id, aiAccount.id, 'AcrPull')
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: aiAccount.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Agent base model deployment -------------------------------------------

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiAccount
  name: modelDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 50
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1-mini'
      version: '2025-04-14'
    }
  }
}

// --- Optimizer model deployment (Agent Optimizer) --------------------------
// The optimizer needs a GPT-5.x model. It is deployed serially after the base
// model because Cognitive Services does not allow parallel deployments.

resource optimizerDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiAccount
  name: 'gpt-5.1'
  dependsOn: [modelDeployment]
  sku: {
    name: 'Standard'
    capacity: 50
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.1'
      version: '2025-11-13'
    }
  }
}

// --- Connect App Insights to the Foundry project (enables Traces tab) ------
// The Foundry portal's Traces/Monitor tabs require an 'AppInsights' connection
// on the project. The credential key must be the App Insights connection string.

resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: aiProject
  name: 'appinsights'
  properties: {
    category: 'AppInsights'
    target: appInsights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: appInsights.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsights.id
    }
  }
}

output projectEndpoint string = 'https://${aiAccount.name}.services.ai.azure.com/api/projects/${aiProject.name}'
output projectId string = aiProject.id
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output containerRegistryEndpoint string = containerRegistry.properties.loginServer
output containerRegistryName string = containerRegistry.name
