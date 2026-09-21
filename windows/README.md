# Horários Família — Windows

Aplicação nativa para Windows que apresenta a mesma aplicação Horários Família publicada no GitHub Pages.

## Características

- Todas as funcionalidades da aplicação web/PWA são reutilizadas diretamente.
- Atualizações de conteúdos e novas builds web chegam automaticamente sem reinstalar o EXE.
- Localização via serviços de localização do Windows/WebView2, com o mesmo fallback por rede/IP da aplicação web.
- Meteorologia, paletas sazonais e modo noturno automático.
- Agenda desportiva, calendários, horários e eventos familiares.
- Reprodução de áudio/podcast.
- Ligações externas abrem no browser predefinido do Windows.
- F5 ou Ctrl+R: atualização forçada da aplicação.
- F11: ecrã inteiro; Esc: sair do ecrã inteiro.
- Alt+Esquerda / Alt+Direita: navegação.

## Tecnologia

O invólucro nativo usa .NET 8 WinForms + Microsoft Edge WebView2. O executável publicado pelo GitHub Actions é self-contained para Windows x64; não exige uma instalação separada do .NET.

O Microsoft Edge WebView2 Runtime deve estar disponível. Em Windows 10/11 com Microsoft Edge atualizado, normalmente já está instalado.

## Compilação

O workflow .github/workflows/build-windows.yml gera HorariosFamilia-Windows.exe e publica-o na release estável Horários Família — Windows.
