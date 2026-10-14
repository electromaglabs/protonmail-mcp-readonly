Feature: Bilagekatalogen skyddar filsystemet
  Som användare som låter en AI-klient spara och skicka bilagor
  vill jag att all filåtkomst stannar i en egen bilagekatalog
  så att ett mejl eller en felaktig sökväg inte kan läsa eller skriva andra filer.

  Scenario: Katalogen skapas vid behov med rättigheter bara för ägaren
    Given en bilagekatalog som inte finns ännu
    When en bilaga sparas med filnamnet "faktura.pdf"
    Then ska bilagekatalogen finnas med rättigheterna 700
    And ska filen "faktura.pdf" finnas i bilagekatalogen

  Scenario: Avsändarens filnamn med sökväg saneras till ett rent filnamn
    Given en tom bilagekatalog
    When en bilaga sparas med filnamnet "../../.ssh/authorized_keys"
    Then ska filen "authorized_keys" finnas i bilagekatalogen
    And ska inget ha skrivits utanför bilagekatalogen

  Scenario: Avsändarens filnamn med Windows-sökväg saneras
    Given en tom bilagekatalog
    When en bilaga sparas med filnamnet "..\\..\\Windows\\evil.bat"
    Then ska filen "evil.bat" finnas i bilagekatalogen

  Scenario: Kontrolltecken och riktningsmarkörer tas bort ur avsändarens filnamn
    Given en tom bilagekatalog
    When en bilaga sparas med filnamnet "rapport‮fdp.exe\n"
    Then ska filen "rapportfdp.exe" finnas i bilagekatalogen

  Scenario: Ett filnamn som bara är punkter blir ett neutralt namn
    Given en tom bilagekatalog
    When en bilaga av typen "application/pdf" sparas med filnamnet ".."
    Then ska filen "bilaga.pdf" finnas i bilagekatalogen

  Scenario: Namnkrock ger ett suffix och skriver aldrig över en befintlig fil
    Given en bilagekatalog som redan innehåller "faktura.pdf" med innehållet "gammal"
    When en bilaga sparas med filnamnet "faktura.pdf"
    Then ska filen "faktura (1).pdf" finnas i bilagekatalogen
    And ska "faktura.pdf" fortfarande ha innehållet "gammal"

  Scenario: En symlänk med bilagans namn följs inte vid sparning
    Given en tom bilagekatalog
    And en symlänk "faktura.pdf" i bilagekatalogen som pekar på en fil utanför
    When en bilaga sparas med filnamnet "faktura.pdf"
    Then ska filen "faktura (1).pdf" finnas i bilagekatalogen
    And ska filen utanför vara orörd

  Scenario: En fil i bilagekatalogen kan väljas för att skickas
    Given en tom bilagekatalog
    And filen "offert.pdf" i bilagekatalogen
    When jag väljer filen "offert.pdf" att skicka
    Then ska den valda filen vara "offert.pdf" i bilagekatalogen

  Scenario: En absolut sökväg inom bilagekatalogen godtas
    Given en tom bilagekatalog
    And filen "offert.pdf" i bilagekatalogen
    When jag väljer den absoluta sökvägen till "offert.pdf" att skicka
    Then ska den valda filen vara "offert.pdf" i bilagekatalogen

  Scenario: Path traversal ut ur bilagekatalogen avvisas
    Given en tom bilagekatalog
    And en fil "hemlig.txt" utanför bilagekatalogen
    When jag väljer filen "../hemlig.txt" att skicka
    Then ska valet avvisas med ett fel som nämner "bilagekatalogen"

  Scenario: En absolut sökväg utanför bilagekatalogen avvisas
    Given en tom bilagekatalog
    And en fil "hemlig.txt" utanför bilagekatalogen
    When jag väljer den absoluta sökvägen till filen utanför att skicka
    Then ska valet avvisas med ett fel som nämner "bilagekatalogen"

  Scenario: En symlänk som pekar ut ur bilagekatalogen avvisas
    Given en tom bilagekatalog
    And en symlänk "genvag.txt" i bilagekatalogen som pekar på en fil utanför
    When jag väljer filen "genvag.txt" att skicka
    Then ska valet avvisas med ett fel som nämner "bilagekatalogen"

  Scenario: Ett filnamn med kontrolltecken avvisas
    Given en tom bilagekatalog
    When jag väljer filen "offert\n.pdf" att skicka
    Then ska valet avvisas med ett fel som nämner "kontrolltecken"

  Scenario: En fil som inte finns ger ett begripligt fel
    Given en tom bilagekatalog
    When jag väljer filen "saknas.pdf" att skicka
    Then ska valet avvisas med ett fel som nämner "finns inte"

  Scenario: En katalog kan inte skickas som bilaga
    Given en tom bilagekatalog
    And underkatalogen "mapp" i bilagekatalogen
    When jag väljer filen "mapp" att skicka
    Then ska valet avvisas med ett fel som nämner "inte en vanlig fil"

  Scenario: Bilagekatalogen kan ställas in med PROTONMAIL_ATTACHMENT_DIR
    Given att PROTONMAIL_ATTACHMENT_DIR pekar på en egen katalog
    When inställningarna läses
    Then ska bilagekatalogen vara den katalogen

  Scenario: Utan inställning används ~/Downloads/protonmail-mcp
    Given att PROTONMAIL_ATTACHMENT_DIR inte är satt
    When inställningarna läses
    Then ska bilagekatalogen vara "~/Downloads/protonmail-mcp" i hemkatalogen
