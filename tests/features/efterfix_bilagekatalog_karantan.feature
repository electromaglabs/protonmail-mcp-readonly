Feature: Sparade bilagor karantänmärks på macOS
  Som macOS-användare som öppnar bilagor som get_attachment har sparat
  vill jag att filerna märks com.apple.quarantine precis som i Mail och Safari
  så att Gatekeeper och Terminal varnar innan en .terminal-fil eller en app ur en zip körs.

  Scenario: En sparad bilaga får karantänmärkning på macOS
    Given att servern körs på macOS
    And en tom bilagekatalog för karantän
    When bilagan "Faktura.terminal" sparas
    Then ska den sparade filen ha karantänmärkning från "protonmail-mcp"
    And ska märkningen ha flaggorna "0083" och aktuell tid

  Scenario: På andra plattformar sparas bilagan utan märkning
    Given att servern körs på Linux
    And en tom bilagekatalog för karantän
    When bilagan "Faktura.terminal" sparas
    Then ska bilagan ha sparats
    And ska ingen karantänmärkning ha försökts

  Scenario: Om märkningen misslyckas sparas bilagan ändå, med en varning i loggen
    Given att servern körs på macOS
    And att karantänmärkning inte går att sätta
    And en tom bilagekatalog för karantän
    When bilagan "Faktura.terminal" sparas
    Then ska bilagan ha sparats
    And ska loggen varna för att karantänmärkningen misslyckades
