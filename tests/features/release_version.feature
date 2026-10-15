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
