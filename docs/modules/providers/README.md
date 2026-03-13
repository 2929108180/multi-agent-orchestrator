# Providers Module

## Current Capabilities

- official provider adapters
- Packy-specific profile support
- direct API and `base_url` gateway usage
- responses / messages / generate_content routing

## Current Notes

- Packy GPT is not treated the same as official OpenAI
- Packy Gemini and Packy Claude can require their own request shapes
- provider profiles prevent one gateway quirk from affecting every provider

## Next Improvements

- more gateway profiles
- richer health checks by provider profile
- direct request replay tools
