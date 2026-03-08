// infrastructure/main.bicep
targetScope = 'resourceGroup'

@description('Environment name (dev, prod)')
param environment string = 'dev'

@description('Location')
param location string = resourceGroup().location

@description('Principal ID for Key Vault access')
param principalId string

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

output storageAccountName string = storage.outputs.storageAccountName
output storageConnectionString string = storage.outputs.connectionString
output keyVaultUri string = keyvault.outputs.keyVaultUri
