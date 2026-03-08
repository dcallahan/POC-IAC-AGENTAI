// infrastructure/modules/containerapp.bicep
@description('Name of the Container App')
param containerAppName string

@description('Location')
param location string = resourceGroup().location

@description('Container Apps Environment ID')
param environmentId string

@description('ACR login server (e.g. myacr.azurecr.io)')
param acrLoginServer string

@description('ACR admin username')
param acrUsername string

@description('ACR admin password')
@secure()
param acrPassword string

@description('Container image name:tag')
param imageName string = 'iga-agent:latest'

@description('CPU cores')
param cpu string = '1.0'

@description('Memory')
param memory string = '2.0Gi'

@description('Minimum replicas (0 = scale to zero)')
param minReplicas int = 0

@description('Maximum replicas')
param maxReplicas int = 3

@description('Azure AI Foundry resource name')
param foundryResource string

@description('Storage connection string')
@secure()
param storageConnectionString string

@description('Foundry API key')
@secure()
param foundryApiKey string

@description('Teams webhook URL')
@secure()
param teamsWebhookUrl string

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      registries: [
        {
          server: acrLoginServer
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acrPassword
        }
        {
          name: 'foundry-api-key'
          value: foundryApiKey
        }
        {
          name: 'storage-connection-string'
          value: storageConnectionString
        }
        {
          name: 'teams-webhook-url'
          value: teamsWebhookUrl
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'iga-agent'
          image: '${acrLoginServer}/${imageName}'
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            {
              name: 'FOUNDRY_API_KEY'
              secretRef: 'foundry-api-key'
            }
            {
              name: 'FOUNDRY_RESOURCE'
              value: foundryResource
            }
            {
              name: 'AZURE_STORAGE_CONNECTION_STRING'
              secretRef: 'storage-connection-string'
            }
            {
              name: 'TEAMS_WEBHOOK_URL'
              secretRef: 'teams-webhook-url'
            }
            {
              name: 'PORT'
              value: '8000'
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '3'
              }
            }
          }
        ]
      }
    }
  }
}

output containerAppId string = containerApp.id
output containerAppName string = containerApp.name
output fqdn string = containerApp.properties.configuration.ingress.fqdn
output latestRevisionFqdn string = containerApp.properties.latestRevisionFqdn
