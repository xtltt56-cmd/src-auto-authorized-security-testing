import type { TargetDraft } from './types'

export const blankTargetDraft: TargetDraft = {
  projectName: '',
  targetUrl: '',
  allowedHosts: '',
  allowedPorts: '',
  excludedPaths: '',
  windowStart: '',
  windowEnd: '',
  allowedMethods: 'GET, HEAD',
  concurrency: '1',
  requestLimit: '100',
  authorizationNote: '',
}
