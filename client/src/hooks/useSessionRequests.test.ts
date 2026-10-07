import { act, renderHook } from '@testing-library/react'
import { apiFetch } from '../api'
import { useSessionRequests } from './useSessionRequests'

jest.mock('../api', () => ({ apiFetch: jest.fn() }))
const fetchMock = apiFetch as jest.MockedFunction<typeof apiFetch>
const response = (data: any, ok = true) => ({ ok, json: async () => data } as Response)

beforeEach(() => fetchMock.mockReset())

test('shares session creation until the campaign list catches up', async () => {
  let resolve!: (response: Response) => void
  fetchMock.mockReturnValue(new Promise(done => { resolve = done }))
  const { result, rerender } = renderHook(() => useSessionRequests())
  const first = result.current.ensureCampaignSession('a')
  rerender()
  expect(result.current.ensureCampaignSession('a')).toBe(first)
  await act(async () => { resolve(response({ session_id: 's' })); await first })
  expect(await result.current.ensureCampaignSession('a')).toEqual({ session_id: 's' })
  expect(fetchMock).toHaveBeenCalledTimes(1)
  result.current.forgetCampaignSession('a')
  fetchMock.mockResolvedValue(response({ session_id: 'new' }))
  expect(await result.current.ensureCampaignSession('a')).toEqual({ session_id: 'new' })
})

test('failed creation can retry and campaigns have independent requests', async () => {
  fetchMock.mockResolvedValueOnce(response({}, false)).mockResolvedValue(response({ session_id: 's' }))
  const { result } = renderHook(() => useSessionRequests())
  await expect(result.current.ensureCampaignSession('a')).rejects.toThrow()
  await result.current.ensureCampaignSession('a')
  await result.current.ensureCampaignSession('b')
  expect(fetchMock).toHaveBeenCalledTimes(3)
})

test('shares pending metadata but rereads after a response or failure', async () => {
  let resolve!: (response: Response) => void
  fetchMock.mockReturnValueOnce(new Promise(done => { resolve = done }))
  const { result } = renderHook(() => useSessionRequests())
  const first = result.current.loadSessionMeta('s')
  expect(result.current.loadSessionMeta('s')).toBe(first)
  resolve(response({ name: 'old' }))
  await first
  fetchMock.mockResolvedValueOnce(response({}, false)).mockResolvedValue(response({ name: 'updated' }))
  await expect(result.current.loadSessionMeta('s')).rejects.toThrow()
  expect(await result.current.loadSessionMeta('s')).toEqual({ name: 'updated' })
  expect(fetchMock).toHaveBeenCalledTimes(3)
})
