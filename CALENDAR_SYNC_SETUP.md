# Sincronização privada das agendas de Carlos e Sandrinha

A aplicação mostra os eventos dos dois calendários numa linha global entre **Meteorologia** e **Família**.

Os dados são sincronizados automaticamente de 10 em 10 minutos e ficam encriptados no ficheiro público `personal-calendar.enc.json`. Os endereços privados dos calendários e o código de desencriptação ficam apenas nos GitHub Actions Secrets.

## 1. Obter os dois endereços iCal privados

Em cada conta Google:

1. Abrir o Google Calendar no computador.
2. **Definições** → escolher o calendário principal da pessoa.
3. **Integrar calendário**.
4. Copiar **Endereço secreto em formato iCal**.

Fazer isto uma vez para o calendário de Carlos e outra para o calendário de Sandrinha.

Nunca colocar estes endereços num ficheiro do repositório nem numa conversa pública.

## 2. Criar três GitHub Actions Secrets

No repositório:

**Settings → Secrets and variables → Actions → New repository secret**

Criar:

- `CARLOS_CALENDAR_ICS_URL` — endereço iCal secreto de Carlos.
- `SANDRINHA_CALENDAR_ICS_URL` — endereço iCal secreto de Sandrinha.
- `PERSONAL_CALENDAR_PASSPHRASE` — código longo e exclusivo escolhido pelo utilizador.

O código deve ter idealmente pelo menos 20 caracteres e não deve ser uma palavra-passe usada noutro serviço.

## 3. Fazer a primeira sincronização

Em **Actions → Sincronizar agendas pessoais → Run workflow**.

Depois, o workflow repete a sincronização automaticamente a cada 10 minutos.

## 4. Ligar cada dispositivo

Quando a app detetar um ficheiro de agenda configurado, apresenta **Agenda pessoal · Ligar**.

Introduzir o mesmo `PERSONAL_CALENDAR_PASSPHRASE`. O código é guardado apenas nesse dispositivo.

## Privacidade e filtro desportivo

- O conteúdo dos eventos nunca é gravado em texto simples no GitHub.
- A app identifica visualmente cada evento como **CARLOS** ou **SANDRINHA**.
- Apenas os calendários pessoais indicados pelos dois endereços iCal são importados.
- O sincronizador elimina eventos identificados como desportivos por modalidade, competição, equipas e fontes desportivas conhecidas antes da encriptação.
