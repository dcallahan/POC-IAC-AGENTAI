// infrastructure/parameters/dev.bicepparam
using '../main.bicep'

param environment = 'dev'
param location = 'eastus2'
param principalId = '' // Fill with your service principal object ID
param foundryResource = ''    // Fill: your AI Foundry resource name
param foundryApiKey = ''      // Fill: your Foundry API key
param teamsWebhookUrl = ''    // Fill: your Teams webhook URL
