// infrastructure/modules/acr.bicep
@description('Name of the Container Registry (must be globally unique, alphanumeric)')
param registryName string

@description('Location')
param location string = resourceGroup().location

@description('SKU for the registry')
@allowed(['Basic', 'Standard', 'Premium'])
param sku string = 'Basic'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  sku: {
    name: sku
  }
  properties: {
    adminUserEnabled: true
  }
}

output registryId string = acr.id
output registryName string = acr.name
output loginServer string = acr.properties.loginServer
output adminUsername string = acr.listCredentials().username
output adminPassword string = acr.listCredentials().passwords[0].value
