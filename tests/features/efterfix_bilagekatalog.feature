Feature: Bilagekatalogen går inte att kapa
  Som användare som låter en AI-klient skicka filer ur bilagekatalogen
  vill jag att katalogen inte kan bytas ut mot en symlänk eller delas med andra
  så att en uppackad zip eller en prompt-injektion inte kan få mina nycklar skickade.

  Background:
    Given en hemkatalog med en privat nyckel i ".ssh/id_ed25519" och en hemlighet i "projekt/.env"

  Scenario: En bilagekatalog som är en symlänk till hemkatalogen avvisas vid sändning
    Given att bilagekatalogen är symlänken "Downloads/protonmail-mcp" som pekar på ".."
    When jag försöker skicka filen ".ssh/id_ed25519" som bilaga
    Then ska sändningen avvisas med ett fel som nämner "symlänk"

  Scenario: En absolut sökväg in i hemkatalogen avvisas när bilagekatalogen är en symlänk
    Given att bilagekatalogen är symlänken "Downloads/protonmail-mcp" som pekar på ".."
    When jag försöker skicka den absoluta sökvägen till ".ssh/id_ed25519" som bilaga
    Then ska sändningen avvisas med ett fel som nämner "symlänk"

  Scenario: Ingenting sparas när bilagekatalogen är en symlänk
    Given att bilagekatalogen är symlänken "Downloads/protonmail-mcp" som pekar på ".."
    When en bilaga sparas med filnamnet "authorized_keys"
    Then ska sparningen avvisas med ett fel som nämner "symlänk"
    And ska ingen ny fil finnas i hemkatalogen

  Scenario: En bilagekatalog som ligger under en symlänk avvisas
    Given att "Downloads" är en symlänk till hemkatalogen
    And att bilagekatalogen är "Downloads/protonmail-mcp" med filen "offert.pdf"
    When jag försöker skicka filen "offert.pdf" som bilaga
    Then ska sändningen avvisas med ett fel som nämner "symlänk"

  Scenario: En bilagekatalog som andra kan skriva i avvisas
    Given att bilagekatalogen är "Downloads/protonmail-mcp" med filen "offert.pdf"
    And att bilagekatalogen har rättigheterna 777
    When jag försöker skicka filen "offert.pdf" som bilaga
    Then ska sändningen avvisas med ett fel som nämner "skrivbar"

  Scenario: En bilagekatalog som ägs av någon annan avvisas
    Given att bilagekatalogen är "Downloads/protonmail-mcp" med filen "offert.pdf"
    And att bilagekatalogen ägs av en annan användare
    When jag försöker skicka filen "offert.pdf" som bilaga
    Then ska sändningen avvisas med ett fel som nämner "ägs inte av dig"

  Scenario: En relativ PROTONMAIL_ATTACHMENT_DIR avvisas
    Given att PROTONMAIL_ATTACHMENT_DIR är "bilagor"
    When inställningarna läses in
    Then ska inläsningen misslyckas med ett fel som nämner "absolut"

  Scenario: Bilagekatalogen skapas när servern startar
    Given att PROTONMAIL_ATTACHMENT_DIR pekar på "Downloads/protonmail-mcp" som inte finns
    When servern startar
    Then ska bilagekatalogen finnas med rättigheterna 700

  Scenario: Servern startar även när bilagekatalogen är en symlänk, men varnar
    Given att bilagekatalogen är symlänken "Downloads/protonmail-mcp" som pekar på ".."
    When servern startar
    Then ska servern ha startat
    And ska loggen varna för bilagekatalogen
    And ska symlänken "Downloads/protonmail-mcp" vara kvar

  Scenario: En hård länk till en fil utanför bilagekatalogen skickas inte
    Given att bilagekatalogen är "Downloads/protonmail-mcp" med filen "offert.pdf"
    And en hård länk "kopia.txt" i bilagekatalogen till "projekt/anteckning.txt" i hemkatalogen
    When jag försöker skicka filen "kopia.txt" som bilaga
    Then ska sändningen avvisas med ett fel som nämner "hårda länkar"

  Scenario Outline: Filer som ser ut att innehålla hemligheter skickas inte
    Given att bilagekatalogen är "Downloads/protonmail-mcp" med filen "<fil>"
    When jag försöker skicka filen "<fil>" som bilaga
    Then ska sändningen avvisas med ett fel som nämner "hemligheter"

    Examples:
      | fil                    |
      | .env                   |
      | projekt/.env           |
      | .env.local             |
      | .ssh/config            |
      | .gnupg/pubring.kbx     |
      | id_ed25519             |
      | id_rsa.pub             |
      | server.pem             |
      | privat.key             |
      | .netrc                 |
      | .aws/credentials       |
      | login.keychain-db      |
      | Keychains/login.db     |

  Scenario: En privat nyckel med ett oskyldigt filnamn skickas inte
    Given att bilagekatalogen är "Downloads/protonmail-mcp" med filen "faktura.txt"
    And att "faktura.txt" i bilagekatalogen innehåller en privat OpenSSH-nyckel
    When jag försöker skicka filen "faktura.txt" som bilaga
    Then ska sändningen avvisas med ett fel som nämner "hemligheter"

  Scenario Outline: Vanliga filer med liknande namn går att skicka
    Given att bilagekatalogen är "Downloads/protonmail-mcp" med filen "<fil>"
    When jag försöker skicka filen "<fil>" som bilaga
    Then ska en bilaga med namnet "<namn>" ha byggts

    Examples:
      | fil                  | namn                 |
      | id_kort.pdf          | id_kort.pdf          |
      | environment.txt      | environment.txt      |
      | nyckeltal.xlsx       | nyckeltal.xlsx       |
      | rapport/offert.pdf   | offert.pdf           |
