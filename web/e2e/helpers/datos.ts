/** Email único por corrida para que `npm run e2e` se pueda repetir contra el mismo `docker
 * compose` (misma base) sin chocar con `email_en_uso` de una corrida anterior.
 *
 * El dominio NO puede ser `.test`/`.invalid`/`.localhost` (RFC 2606, de uso reservado): la
 * validación de `EmailStr` del backend (paquete `email-validator`) los rechaza con 422 aunque
 * la sintaxis sea válida -- confirmado corriendo el e2e de punta a punta, no solo leyendo el
 * código. */
export function emailUnico(prefijo: string): string {
  return `${prefijo}-${Date.now()}-${Math.floor(Math.random() * 1_000_000)}@e2e-predicts.com`
}
