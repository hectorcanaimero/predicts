import { createRootRoute, Outlet } from '@tanstack/react-router'

/** La raíz no agrega estructura: las rutas públicas usan `LayoutPublico` y las autenticadas
 * `ShellApp` (barra lateral + encabezado), cada una con su propio selector de idioma. */
export const Route = createRootRoute({ component: Outlet })
