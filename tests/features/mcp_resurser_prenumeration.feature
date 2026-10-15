Feature: Prenumerera på ändringar i resurser
  Som MCP-klient
  vill jag kunna prenumerera på en mapp eller ett mejl
  så att jag får en notis när den ändras (t.ex. när nya mejl kommer)
  i stället för att behöva läsa om resursen hela tiden.

  Scenario: Servern annonserar att resurser går att prenumerera på
    When klienten ansluter
    Then ska serverns förmågor ha resources.subscribe satt

  Scenario: En prenumerant får en notis när mappen ändras
    Given att klienten prenumererar på mappresursen för "Labels/Näs Samfällighet"
    When servern meddelar att mappresursen för "Labels/Näs Samfällighet" har ändrats
    Then ska klienten få en notis om att "mailbox://Labels%2FN%C3%A4s%20Samf%C3%A4llighet" har ändrats

  Scenario: Ingen notis om en resurs man inte prenumererar på
    Given att klienten prenumererar på mappresursen för "INBOX"
    When servern meddelar att mappresursen för "Archive" har ändrats
    Then ska klienten inte få någon notis

  Scenario: Ingen notis efter avslutad prenumeration
    Given att klienten prenumererar på mappresursen för "INBOX"
    And att klienten avslutar prenumerationen på mappresursen för "INBOX"
    When servern meddelar att mappresursen för "INBOX" har ändrats
    Then ska klienten inte få någon notis

  Scenario: Notisen använder URI:n som klienten prenumererade med
    Given att klienten prenumererar på resursen "mailbox://Folders/A/B"
    When servern meddelar att mappresursen för "Folders/A/B" har ändrats
    Then ska klienten få en notis om att "mailbox://Folders/A/B" har ändrats

  Scenario: En stängd session städas bort
    Given att en klient som prenumererar på mappresursen för "INBOX" har kopplat ner
    When servern meddelar att mappresursen för "INBOX" har ändrats
    Then ska meddelandet inte misslyckas
    And ska ingen prenumeration finnas kvar på mappresursen för "INBOX"

  Scenario: Ett fel i en session stoppar inte de andra
    Given att två sessioner prenumererar på mappresursen för "INBOX"
    And att notisen till den första sessionen misslyckas
    When servern meddelar att mappresursen för "INBOX" har ändrats
    Then ska den andra sessionen ändå få notisen

  Scenario: Prenumeration på en okänd resurs vägras
    When klienten försöker prenumerera på resursen "file:///etc/passwd"
    Then ska prenumerationen misslyckas med texten "Okänd resurs"
