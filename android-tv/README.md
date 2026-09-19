# Horários Família — Android TV

Este módulo cria um APK para Android TV/Google TV. O APK abre a versão publicada em GitHub Pages
com o modo TV ativo, navegação por comando remoto e um perfil de ecrã guardado localmente.

Perfis:
- sala40 — sala, TV Samsung UE40B7000 (40 polegadas)
- quarto49 — quarto, TV Samsung UE49MU6225 (49 polegadas)
- cozinha-auto — cozinha, perfil adaptativo pela resolução/viewport
- auto — deteção genérica

As alterações normais da aplicação web não exigem nova instalação do APK. Quando o GitHub Pages
publica uma nova versão, a própria aplicação verifica version.json e recarrega a versão nova.
Só é necessário reinstalar o APK se o código do invólucro Android TV for alterado.
