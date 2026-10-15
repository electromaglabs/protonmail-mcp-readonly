Feature: Servern går att starta med python -m protonmail_mcp
  Som användare som startar MCP-servern
  vill jag kunna starta den med python -m protonmail_mcp (paketets namn)
  eftersom det är det vanliga sättet att köra ett Python-paket som program,
  och en server som inte startar alls är värre än en som saknar en funktion.

  Scenario: Servern startad som paket har samma verktyg, resurser och promptar
    When servern startas med "python -m protonmail_mcp"
    Then ska den startade servern ha samma verktyg som med kommandot protonmail-mcp
    And ska den startade servern ha resursen "mailboxes://" och prenumerationer på resurser
    And ska den startade servern ha promptarna "sammanfatta_olasta, triagera_inkorgen, svara_pa_mejl, rensa_nyhetsbrev"
