Feature: Sökresultatet innehåller bara brev som faktiskt hämtades
  Som en MCP-klient
  vill jag att varje träff i ett sökresultat är ett riktigt brev med headers
  så att jag inte får fantommejl eller dubbletter.

  Scenario: En flaggändring från en annan klient under sökningen blir inget fantommejl
    Given att en sökning i INBOX träffar brev 1 och 2 med UID "20" och "30"
    And servern skickar en oombedd flaggändring för UID "999" mitt i svaret
    When jag söker efter olästa brev
    Then ska träffarna ha UID "30" och "20"

  Scenario: Samma brev två gånger i svaret ger en träff
    Given att en sökning i INBOX träffar brev 1 och 2 med UID "20" och "30"
    And servern skickar brevet med UID "20" en gång till
    When jag söker efter olästa brev
    Then ska träffarna ha UID "30" och "20"

  Scenario: UID efter header-datat, som Bridge skickar vid UID FETCH
    Given att servern lägger UID efter header-datat för brevet med UID "11319"
    When jag söker efter olästa brev
    Then ska träffarna ha UID "11319"
    And ska träffen ha ämnet "Hej"
