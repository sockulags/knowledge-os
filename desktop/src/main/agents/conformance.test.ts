import { PROVIDERS } from './providers'
import { describeConformance } from './testing/conformance'

// Every provider the app offers passes the same suite.
for (const provider of PROVIDERS) describeConformance(provider)
