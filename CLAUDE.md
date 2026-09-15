# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working
with code in this repository.

@AGENTS.md

## Ce projet en une phrase

POC Python qui interroge l'API du plugin GoodPrice d'un serveur Eco pour
trouver les routes et chaines de trading rentables, en tenant compte des
contraintes reelles (solde des acheteurs partage par joueur, stocks,
blacklists) et en signalant les contreparties inactives.

## Avant de modifier un calcul

Les regles du modele economique sont documentees et justifiees dans
`docs/modele-economique.md`, et chacune est couverte par un test. Elles
viennent de la lecture du plugin (`../source/`) et de l'observation de
snapshots reels (`../outputs/`), pas d'hypotheses. Si un chiffre semble
faux, verifier d'abord le snapshot de reference plutot que de changer la
formule.
