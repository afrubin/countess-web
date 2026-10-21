// Fails if src/api-schema.ts is not what openapi.json generates: run `npm run generate:api`.
import { readFileSync } from 'node:fs'
import openapiTS, { astToString } from 'openapi-typescript'

const schema = new URL('../openapi.json', import.meta.url)
const generated = new URL('../src/api-schema.ts', import.meta.url)

const expected = astToString(await openapiTS(schema))
const committed = readFileSync(generated, 'utf8')
if (committed.replace(/^\/\*\*[\s\S]*?\*\/\n\n/, '') !== expected) {
  console.error('src/api-schema.ts is out of date with openapi.json: run `npm run generate:api`.')
  process.exit(1)
}
