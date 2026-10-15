Feature: Begripligt fel när ett mapp- eller etikettnamn redan används
  Som en MCP-klient
  vill jag få veta varför create_folder misslyckas när namnet är upptaget
  eftersom Proton kräver unika namn över mappar och etiketter tillsammans.

  Scenario: En mapp med samma namn som en befintlig etikett
    Given att etiketten "Labels/Kvitton" finns
    And att Bridge nekar CREATE med Protons fel för upptaget namn
    When jag skapar "Folders/Kvitton"
    Then ska felet förklara på svenska att namnet redan används av "Labels/Kvitton"
