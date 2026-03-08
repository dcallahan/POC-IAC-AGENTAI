// infrastructure/modules/loganalytics.bicep
@description('Name of the Log Analytics workspace')
param workspaceName string

@description('Location')
param location string = resourceGroup().location

@description('Retention in days')
param retentionInDays int = 30

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionInDays
  }
}

output workspaceId string = workspace.id
output workspaceName string = workspace.name
output customerId string = workspace.properties.customerId
output sharedKey string = workspace.listKeys().primarySharedKey
