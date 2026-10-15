Feature: Dokumentationen stämmer med koden
  Som användare som läser README.md, eller agent som läser CLAUDE.md,
  vill jag att verktyg, resurser, promptar, inställningar och moduler som
  dokumentationen nämner är exakt de som finns i koden
  så att jag inte letar efter ett verktyg som inte finns eller missar en spärr.

  Scenario: README listar exakt de verktyg som servern registrerar
    Given README.md och den registrerade servern
    Then ska verktygstabellerna i README.md innehålla exakt serverns verktyg

  Scenario: README anger rätt effekt för varje verktyg
    Given README.md och den registrerade servern
    Then ska effektkolumnen för varje verktyg stämma med verktygets annoteringar

  Scenario: README listar alla inställningar med rätt standardvärde
    Given README.md och den registrerade servern
    Then ska inställningstabellen i README.md innehålla exakt inställningarna i config.py
    And ska varje inställnings standardvärde stämma med config.py

  Scenario: README listar resurserna och promptarna
    Given README.md och den registrerade servern
    Then ska resurstabellen i README.md innehålla exakt serverns resurser och resursmallar
    And ska prompttabellen i README.md innehålla exakt serverns promptar

