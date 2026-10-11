@echo off
rem Copy to config\run.local.bat and replace the placeholders. Never commit that file.
set "GMAIL_OAUTH_CLIENT_FILE=C:\private\gmail-oauth-client.json"
set "GMAIL_TOKEN_FILE=C:\private\gmail-token.json"
set "GMAIL_SEARCH_QUERY=from:reports@example.invalid subject:Billing"
set "NABLE_CLIENTS_URL=https://YOUR-NABLE-ENDPOINT/clients.xml?apikey=YOUR-KEY"
set "GOOGLE_CREDENTIALS_FILE=C:\private\google-service-account.json"
set "GOOGLE_SHEET_ID=YOUR_SPREADSHEET_ID"
set "GOOGLE_WORKSHEET=XeroIDs"
