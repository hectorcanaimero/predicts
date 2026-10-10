import { render, screen } from '@testing-library/react'
import { fireEvent } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useTranslation } from 'react-i18next'

import '../i18n'
import { LanguageSwitcher } from '../routes/__root'

function PaginaDePrueba() {
  const { t } = useTranslation()
  return (
    <div>
      <LanguageSwitcher />
      <p>{t('bienvenida')}</p>
    </div>
  )
}

describe('selector de idioma', () => {
  it('cambia el texto mostrado entre pt-BR, es y en', () => {
    render(<PaginaDePrueba />)

    fireEvent.click(screen.getByRole('button', { name: 'Português' }))
    expect(screen.getByText('Bem-vindo ao predicts')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Español' }))
    expect(screen.getByText('Bienvenido a predicts')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'English' }))
    expect(screen.getByText('Welcome to predicts')).toBeTruthy()
  })
})
