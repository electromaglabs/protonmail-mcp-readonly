Feature: Mappnamn med specialtecken
  Som en MCP-klient
  vill jag kunna använda mappar vars namn innehåller "%", "*" eller ".."
  eftersom Proton tillåter dem och det inte finns något filsystem bakom Bridge.

  Scenario: Namn med procent, asterisk och två punkter går att använda
    Given att Bridge listar mappen "Labels/100% klart"
    And att Bridge listar mappen "Folders/Viktigt*"
    And att Bridge listar mappen "Folders/v1..v2"
    When jag listar mapparna
    And jag hämtar status för varje listad mapp
    Then ska Bridge ha fått tillbaka exakt de namn som listades

  Scenario: Namn med radbrytning avvisas utan att Bridge kontaktas
    When jag hämtar status för en mapp vars namn innehåller en radbrytning
    Then ska anropet avvisas som ogiltigt mailbox-namn
    And ska Bridge inte ha fått något kommando
