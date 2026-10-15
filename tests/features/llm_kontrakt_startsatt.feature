Feature: Alla verktyg finns oavsett hur servern startas
  Som användare som startar MCP-servern
  vill jag att samma verktyg registreras vare sig servern startas med
  kommandot protonmail-mcp eller med python -m protonmail_mcp.server
  eftersom en server utan verktyg ser ut att fungera men inte kan göra något.

  Scenario: Servern startad som modul har alla verktyg
    When servern startas med "python -m protonmail_mcp.server"
    Then ska den startade servern ha samma verktyg som kommandot protonmail-mcp
    And ska den startade servern ha 29 verktyg

  Scenario: Servern startad med kommandot har alla verktyg
    When servern startas med kommandot protonmail-mcp
    Then ska den startade servern ha 29 verktyg
