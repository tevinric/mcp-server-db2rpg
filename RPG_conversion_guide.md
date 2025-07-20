# RPG Traditional to Free-Form Conversion Guide

## Table of Contents
1. [Introduction](#introduction)
2. [Conversion Standards](#conversion-standards)
3. [File Operations](#file-operations)
4. [Data Structures](#data-structures)
5. [Calculations and Logic](#calculations-and-logic)
6. [Subroutines to Procedures](#subroutines-to-procedures)
7. [Error Handling](#error-handling)
8. [Best Practices](#best-practices)
9. [Common Patterns](#common-patterns)
10. [Validation Guidelines](#validation-guidelines)

## Introduction

This guide provides comprehensive standards for converting traditional fixed-format RPG to modern free-form RPG syntax. The conversion should maintain functionality while improving readability and maintainability.

### Conversion Principles
- Maintain 100% functional equivalence
- Improve code readability and structure
- Apply modern RPG best practices
- Ensure compliance with company coding standards
- Document all conversion decisions

## Conversion Standards

### Naming Conventions
- Use descriptive variable names (minimum 8 characters when possible)
- File names should be uppercase
- Procedure names should use camelCase
- Constants should be uppercase with underscores
- Boolean variables should have meaningful prefixes (is, has, can)

### Code Organization
- Group related declarations together
- Separate logical sections with blank lines
- Use consistent indentation (4 spaces)
- Align similar statements for readability
- Comment complex logic thoroughly

## File Operations

### Traditional F-Spec Conversion

**Traditional Format:**
```rpg
F CUSTFILE  IF   E           K DISK
F ORDERFILE UF   E           K DISK    
F TEMPFILE  O    E             DISK
```

**Free-Form Conversion:**
```rpg
DCL-F CUSTFILE DISK(*EXT) USAGE(*INPUT) KEYED;
DCL-F ORDERFILE DISK(*EXT) USAGE(*UPDATE) KEYED;
DCL-F TEMPFILE DISK(*EXT) USAGE(*OUTPUT);
```

### File Declaration Standards
- Always specify USAGE explicitly
- Use KEYED for keyed access methods
- Include TEMPLATE when appropriate
- Use qualified names for better organization
- Document file purpose with comments

**Enhanced Example:**
```rpg
// Customer master file - read only access
DCL-F CUSTFILE DISK(*EXT) USAGE(*INPUT) KEYED TEMPLATE;

// Order transaction file - update operations
DCL-F ORDERFILE DISK(*EXT) USAGE(*UPDATE) KEYED;
```

## Data Structures

### Traditional DS Conversion

**Traditional Format:**
```rpg
D customer       DS
D  custId                        7P 0
D  custName                     50A
D  custAddr                     100A
D  custPhone                    15A
```

**Free-Form Conversion:**
```rpg
DCL-DS customer QUALIFIED TEMPLATE;
    custId PACKED(7:0);
    custName CHAR(50);
    custAddr CHAR(100);
    custPhone CHAR(15);
END-DS;
```

### Data Structure Best Practices
- Always use QUALIFIED data structures
- Create TEMPLATE structures for reusability
- Group related fields logically
- Use descriptive field names
- Document field purposes

**Advanced Example:**
```rpg
// Customer information template
DCL-DS customerTemplate QUALIFIED TEMPLATE;
    identification LIKEDS(customerIdTemplate);
    personalInfo LIKEDS(personalInfoTemplate);
    contactInfo LIKEDS(contactInfoTemplate);
END-DS;

DCL-DS customerIdTemplate QUALIFIED TEMPLATE;
    customerId PACKED(7:0);
    customerType CHAR(2);
    status CHAR(1);
END-DS;
```

## Calculations and Logic

### Arithmetic Operations

**Traditional Format:**
```rpg
C                   EVAL      total = amt1 + amt2
C                   ADD       tax           total
C                   SUB       discount      total
```

**Free-Form Conversion:**
```rpg
total = amt1 + amt2;
total += tax;
total -= discount;
```

### Conditional Logic

**Traditional Format:**
```rpg
C                   IF        custType = 'VIP'
C                   EVAL      discount = total * 0.10
C                   ELSE
C                   EVAL      discount = total * 0.05
C                   ENDIF
```

**Free-Form Conversion:**
```rpg
IF custType = 'VIP';
    discount = total * VIP_DISCOUNT_RATE;
ELSE;
    discount = total * STANDARD_DISCOUNT_RATE;
ENDIF;
```

### Loop Structures

**Traditional Format:**
```rpg
C                   FOR       i = 1 TO maxCount
C                   EVAL      processItem(i)
C                   ENDFOR
```

**Free-Form Conversion:**
```rpg
FOR i = 1 TO maxCount;
    processItem(i);
ENDFOR;
```

## Subroutines to Procedures

### Basic Conversion

**Traditional Subroutine:**
```rpg
C     calcTax      BEGSR
C                   EVAL      tax = amount * TAX_RATE
C                   ENDSR
```

**Free-Form Procedure:**
```rpg
DCL-PROC calcTax;
    DCL-PI *N PACKED(15:2);
        amount PACKED(15:2) CONST;
    END-PI;
    
    RETURN amount * TAX_RATE;
END-PROC;
```

### Advanced Procedure Example

**Complex Subroutine:**
```rpg
C     validateCust BEGSR
C                   EVAL      valid = *OFF
C                   IF        custId > 0 AND custName <> *BLANKS
C                   EVAL      valid = *ON
C                   ENDIF
C                   ENDSR
```

**Modern Procedure:**
```rpg
DCL-PROC validateCustomer;
    DCL-PI *N IND;
        customer LIKEDS(customerTemplate) CONST;
    END-PI;
    
    DCL-S isValid IND INZ(*OFF);
    
    MONITOR;
        IF customer.identification.customerId > 0 
           AND customer.personalInfo.custName <> *BLANKS;
            isValid = *ON;
        ENDIF;
    ON-ERROR;
        isValid = *OFF;
    ENDMON;
    
    RETURN isValid;
END-PROC;
```

## Error Handling

### Traditional Error Handling
```rpg
C                   CHAIN     custId        CUSTFILE
C                   IF        %FOUND(CUSTFILE)
C                   EVAL      custName = CFNAME
C                   ELSE
C                   EVAL      errMsg = 'Customer not found'
C                   ENDIF
```

### Modern Error Handling
```rpg
MONITOR;
    CHAIN custId CUSTFILE;
    IF %FOUND(CUSTFILE);
        customer.personalInfo.custName = CFNAME;
    ELSE;
        DSPLY 'Customer not found: ' + %CHAR(custId);
    ENDIF;
ON-ERROR;
    errorCode = %ERROR;
    errorMessage = 'Database error occurred: ' + %CHAR(errorCode);
    // Log error appropriately
ENDMON;
```

## Best Practices

### Variable Declaration
- Declare variables close to their first use
- Use meaningful names and appropriate data types
- Initialize variables when declared
- Use constants for fixed values

```rpg
// Good examples
DCL-C MAX_CUSTOMERS CONST(9999);
DCL-C VIP_DISCOUNT_RATE CONST(0.10);
DCL-S customerCount INT(10) INZ(0);
DCL-S isValidCustomer IND INZ(*OFF);
```

### Procedure Design
- Keep procedures focused on single responsibilities
- Use parameters instead of global variables
- Return meaningful values
- Include proper error handling

```rpg
DCL-PROC calculateOrderTotal;
    DCL-PI *N PACKED(15:2);
        orderItems LIKEDS(orderItemTemplate) DIM(100) CONST;
        itemCount INT(10) CONST;
        taxRate PACKED(5:4) CONST;
    END-PI;
    
    DCL-S subtotal PACKED(15:2) INZ(0);
    DCL-S tax PACKED(15:2) INZ(0);
    DCL-S i INT(10);
    
    FOR i = 1 TO itemCount;
        subtotal += orderItems(i).quantity * orderItems(i).unitPrice;
    ENDFOR;
    
    tax = subtotal * taxRate;
    RETURN subtotal + tax;
END-PROC;
```

## Common Patterns

### File Processing Pattern

**Traditional:**
```rpg
C                   READ      CUSTFILE
C                   DOW       NOT %EOF(CUSTFILE)
C                   EXSR      ProcessCustomer
C                   READ      CUSTFILE
C                   ENDDO
```

**Free-Form:**
```rpg
READ CUSTFILE;
DOW NOT %EOF(CUSTFILE);
    processCustomer(customer);
    READ CUSTFILE;
ENDDO;
```

### Database Update Pattern

**Traditional:**
```rpg
C                   CHAIN     custId        CUSTFILE
C                   IF        %FOUND(CUSTFILE)
C                   EVAL      CFSTATUS = 'A'
C                   UPDATE    CUSTREC
C                   ENDIF
```

**Free-Form:**
```rpg
MONITOR;
    CHAIN custId CUSTFILE;
    IF %FOUND(CUSTFILE);
        CFSTATUS = CUSTOMER_ACTIVE_STATUS;
        UPDATE CUSTREC;
    ENDIF;
ON-ERROR;
    handleDatabaseError(%ERROR);
ENDMON;
```

## Validation Guidelines

### Pre-Conversion Validation
1. Ensure all source compiles without errors
2. Document all external dependencies
3. Identify all copy members used
4. Note any special compiler directives
5. Document business logic thoroughly

### Post-Conversion Validation
1. Verify successful compilation
2. Test all execution paths
3. Validate business logic equivalence
4. Check performance benchmarks
5. Review code against standards

### Testing Requirements
- Unit testing for all procedures
- Integration testing for file operations
- Performance testing for critical paths
- Error scenario testing
- Regression testing against original functionality

## Conversion Rules Summary

| Traditional Element | Free-Form Equivalent | Notes |
|-------------------|-------------------|-------|
| H-spec | **CTL-OPT | Control specification |
| F-spec | DCL-F | File declaration |
| D-spec | DCL-S, DCL-DS, DCL-C | Data declarations |
| C-spec calculations | Free-form statements | Logic implementation |
| Subroutines | Procedures | Use DCL-PROC/END-PROC |
| BEGSR/ENDSR | DCL-PROC/END-PROC | Convert to procedures |
| EVAL | Direct assignment | No EVAL needed |
| Indicators | Logical variables | Replace with meaningful names |

## Conclusion

This conversion guide provides the framework for successful RPG modernization. Always prioritize:

1. **Functional Equivalence** - Maintain exact business logic
2. **Code Quality** - Improve readability and maintainability  
3. **Standards Compliance** - Follow company coding standards
4. **Documentation** - Document all conversion decisions
5. **Testing** - Thoroughly test converted code

Remember that conversion is an opportunity to improve code quality while maintaining system functionality.

---

*Document Version: 1.0*  
*Last Updated: 2024*  
*Status: Active*