import { useEffect, useState } from 'react'

/** Si la pestaña está visible. Se usa para pausar la animación (`Canvas frameloop="never"`)
 * cuando el usuario cambia de pestaña, para no gastar GPU/batería de fondo. */
export function usePestanaVisible(): boolean {
  const [visible, setVisible] = useState(() => !document.hidden)

  useEffect(() => {
    function actualizar() {
      setVisible(!document.hidden)
    }
    document.addEventListener('visibilitychange', actualizar)
    return () => document.removeEventListener('visibilitychange', actualizar)
  }, [])

  return visible
}
