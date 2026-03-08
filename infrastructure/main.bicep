// infrastructure/main.bicep
targetScope = 'resourceGroup'

@description('Environment name (dev, prod)')
param environment string = 'dev'

@description('Location')
param location string = resourceGroup().location

@description('Principal ID for Key Vault access')
param principalId string

@description('Monthly budget in USD')
param monthlyBudget int = 50

@description('Email addresses for budget alerts')
param budgetContactEmails array = ['derik@callahancs.com']

@description('Azure AI Foundry resource name')
param foundryResource string = ''

@secure()
@description('Azure AI Foundry API key')
param foundryApiKey string = ''

@secure()
@description('Teams incoming webhook URL')
param teamsWebhookUrl string = ''

@description('Container image tag')
param imageTag string = 'latest'

var nameSuffix = 'iga-agent-${environment}'

module storage 'modules/storage.bicep' = {
  name: 'storage-${nameSuffix}'
  params: {
    storageAccountName: replace('st${nameSuffix}', '-', '')
    location: location
  }
}

module keyvault 'modules/keyvault.bicep' = {
  name: 'keyvault-${nameSuffix}'
  params: {
    keyVaultName: 'kv-${nameSuffix}'
    location: location
    principalId: principalId
  }
}

module budget 'modules/budget.bicep' = {
  name: 'budget-${nameSuffix}'
  params: {
    budgetName: 'budget-${nameSuffix}'
    monthlyBudget: monthlyBudget
    contactEmails: budgetContactEmails
    startDate: '2026-03-01'
  }
}

module loganalytics 'modules/loganalytics.bicep' = {
  name: 'loganalytics-${nameSuffix}'
  params: {
    workspaceName: 'log-${nameSuffix}'
    location: location
  }
}

module acr 'modules/acr.bicep' = {
  name: 'acr-${nameSuffix}'
  params: {
    registryName: replace('acr${nameSuffix}', '-', '')
    location: location
  }
}

module containerAppEnv 'modules/containerapp-env.bicep' = {
  name: 'cae-${nameSuffix}'
  params: {
    environmentName: 'cae-${nameSuffix}'
    location: location
    logAnalyticsCustomerId: loganalytics.outputs.customerId
    logAnalyticsSharedKey: loganalytics.outputs.sharedKey
  }
}

module containerApp 'modules/containerapp.bicep' = {
  name: 'aca-${nameSuffix}'
  params: {
    containerAppName: 'aca-${nameSuffix}'
    location: location
    environmentId: containerAppEnv.outputs.environmentId
    acrLoginServer: acr.outputs.loginServer
    acrUsername: acr.outputs.adminUsername
    acrPassword: acr.outputs.adminPassword
    imageName: 'iga-agent:${imageTag}'
    foundryResource: foundryResource
    foundryApiKey: foundryApiKey
    storageConnectionString: storage.outputs.connectionString
    teamsWebhookUrl: teamsWebhookUrl
  }
}

output storageAccountName string = storage.outputs.storageAccountName
output storageConnectionString string = storage.outputs.connectionString
output keyVaultUri string = keyvault.outputs.keyVaultUri
output acrLoginServer string = acr.outputs.loginServer
output containerAppFqdn string = containerApp.outputs.fqdn
output containerAppUrl string = 'https://${containerApp.outputs.fqdn}'
