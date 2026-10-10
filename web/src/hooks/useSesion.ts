import { useQuery } from '@tanstack/react-query'

import { cliente } from '@/api/cliente'

export const CLAVE_SESION = ['sesion'] as const

/** `GET /auth/yo`: `null` sin sesión (401), sin redirigir — lo decide quien use el hook. */
export function useSesion() {
  return useQuery({
    queryKey: CLAVE_SESION,
    queryFn: async () => {
      const { data, response } = await cliente.GET('/auth/yo')
      if (response.status === 401) return null
      return data ?? null
    },
    retry: false,
  })
}
