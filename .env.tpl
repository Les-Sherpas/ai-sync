# MCP server secrets. Used by sync-ai-configs at sync time.
# Values: literal strings or op:// refs (resolved via 1Password).
# In servers.yaml, reference with "${VAR_NAME}".
# Requires OP_ACCOUNT or OP_SERVICE_ACCOUNT_TOKEN for 1Password auth.
#
CONTEXT7_API_KEY=op://Private/AI Tools Secrets/CONTEXT7_API_KEY
EXA_API_KEY=op://Private/AI Tools Secrets/EXA_API_KEY
GOOGLE_OAUTH_CLIENT_ID_PERSO=op://Private/AI Tools Secrets/GOOGLE_OAUTH_CLIENT_ID_PERSO
GOOGLE_OAUTH_CLIENT_SECRET_PERSO=op://Private/AI Tools Secrets/GOOGLE_OAUTH_CLIENT_SECRET_PERSO
GOOGLE_OAUTH_CLIENT_ID_PRO=op://Private/AI Tools Secrets/GOOGLE_OAUTH_CLIENT_ID_PRO
GOOGLE_OAUTH_CLIENT_SECRET_PRO=op://Private/AI Tools Secrets/GOOGLE_OAUTH_CLIENT_SECRET_PRO
GOOGLE_MAPS_GROUNDING_LITE_CLIENT_ID=op://Private/AI Tools Secrets/GOOGLE_MAPS_GROUNDING_LITE_CLIENT_ID
GOOGLE_MAPS_GROUNDING_LITE_CLIENT_SECRET=op://Private/AI Tools Secrets/GOOGLE_MAPS_GROUNDING_LITE_CLIENT_SECRET
