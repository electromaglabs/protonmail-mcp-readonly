Feature: Resurser, promptar och prenumerationer finns oavsett hur servern startas
  Som användare som startar MCP-servern
  vill jag att resurserna, promptarna och prenumerationerna finns vare sig servern
  startas med kommandot protonmail-mcp eller med python -m protonmail_mcp.server.

  Scenario Outline: Servern har resurser, promptar och prenumerationer
    When servern startas med <startsätt>
    Then ska den startade servern ha resursen "mailboxes://"
    And ska den startade servern ha resursmallarna "mailbox://{mailbox}" och "email://{mailbox}/{uid}"
    And ska den startade servern ha promptarna "sammanfatta_olasta, triagera_inkorgen, svara_pa_mejl, rensa_nyhetsbrev"
    And ska den startade servern annonsera prenumerationer på resurser

    Examples:
      | startsätt                         |
      | "python -m protonmail_mcp.server" |
      | kommandot protonmail-mcp          |
