Feature: Versionen anges på ett ställe och stämmer överallt
  Som användare som felsöker eller uppgraderar servern
  vill jag att servern, paketet och ändringsloggen anger samma version
  så att jag vet vilken version jag kör och vad som ändrats i den.

  Scenario: Servern presenterar sig med sin egen version när en klient ansluter
    Given versionen i pyproject.toml
    When en MCP-klient ansluter till servern
    Then ska serverInfo ha namnet "protonmail"
    And ska serverInfo ha versionen ur pyproject.toml, inte MCP-bibliotekets

  Scenario: Paketet anger samma version som pyproject.toml
    Given versionen i pyproject.toml
    Then ska protonmail_mcp.__version__ vara versionen ur pyproject.toml

  Scenario: Ändringsloggen beskriver den aktuella versionen
    Given versionen i pyproject.toml
    And CHANGELOG.md
    Then ska det senaste versionsavsnittet i CHANGELOG.md vara versionen ur pyproject.toml
    And ska varje versionsavsnitt ha ett datum och en länk
    And ska versionsavsnitten stå med den nyaste först

  Scenario: README hänvisar till ändringsloggen
    Given README.md
    Then ska README.md länka till CHANGELOG.md

  Scenario: Installationsinstruktionerna installerar den aktuella versionen
    Given versionen i pyproject.toml
    And README.md
    Then ska README.md ha ett installationskommando som installerar taggen för versionen ur pyproject.toml
    And ska README.md visa hur en befintlig installation uppgraderas till den versionen
    And ska release-notes för versionen finnas och ha samma installationskommando
