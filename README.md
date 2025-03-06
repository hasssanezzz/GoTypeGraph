# GoTypeGraph

## Overview
This project is a Go code structure visualizer that analyzes Go source code to extract structs, interfaces, and their relationships. It then generates a visual representation of these relationships as a graph.


## Output

![Exmaple output](./type-graph.png)
<small>Example ouput ran on [loglens/internal](https://github.com/hasssanezzz/loglens)</small>
- **Green boxes** represent interfaces.
- **White boxes** represent structs.
- An arrow from an interface to a struct means the struct **implements** that interface.
- An arrow from a struct to another struct or interface means the struct **depends on** it.
- **Brown arrows** indicate that a parent struct **uses or returns** the child struct.

## Features
- Parses Go source code to identify:
  - Structs and their fields
  - Interfaces and their methods
  - Method implementations
  - Embedded struct dependencies
- Determines which structs implement which interfaces
- Generates a directed graph visualization of the relationships using Graphviz

## Dependencies
The project requires the following Python libraries:
- `tree_sitter` (for parsing Go code)
- `tree_sitter_go` (Go language grammar for `tree_sitter`)
- `pygraphviz` (for visualizing the structure graph)

You can install the required dependencies using:
```sh
pip install tree_sitter tree_sitter_go pygraphviz
```

## Usage
Run the script with the path to the Go source directory:
```sh
python main.py /path/to/go/project
```
This will analyze the Go project and generate a graph saved as `type-graph.png`.

## How It Works
1. **Code Parsing**: Uses `tree_sitter` to parse Go source files recursively from the given directory.
2. **Data Extraction**:
   - Extracts struct definitions, including fields and embedded structs.
   - Extracts interface definitions and methods.
   - Matches struct methods to interfaces to determine implementation relationships.
3. **Graph Generation**: Uses `pygraphviz` to create a directed graph:
   - Nodes represent structs and interfaces.
   - Edges represent struct dependencies and interface implementations.

## Limitations and Drawbacks
While the project is useful for visualizing Go code structures, it has some limitations:

1. **Cannot Parse Functions as Parameters**  
   - If a method or function takes another function as a parameter (e.g., `func f(callback func(int) int)`), the parser does not handle this correctly.
   - This is because function types require deeper parsing of the Go AST.

2. **Cannot Handle Grouped Parameters**  
   - The parser does not correctly handle grouped parameters like:  
     ```go
     func Example(x, y, z int)
     ```
   - It assumes each parameter has an explicit type (e.g., `func Example(x int, y int, z int)`).
   - This means methods with grouped parameters might be incorrectly parsed or missed.

3. **Limited Type Resolution for Fields**  
   - It does not resolve field types beyond direct name extraction.  
     - Example:  
       ```go
       type A struct {
           B *SomeType
       }
       ```
     - It will capture `"*SomeType"` but does not check if `SomeType` is a struct, an alias, or an imported type.

4. **No Support for Package Imports or Aliases**  
   - The parser does not track imported packages and type aliases, meaning it may misinterpret types from external packages.
   - Example:  
     ```go
     import "mypackage"
     
     type A struct {
         B mypackage.SomeType
     }
     ```
     - It treats `"mypackage.SomeType"` as a raw string without verifying its definition.

5. **No Support for Generics**  
   - The script does not handle Go 1.18+ generics.
   - Example:  
     ```go
     type Box[T any] struct {
         value T
     }
     ```
   - It does not extract `T` properly.

6. **Struct Method Parsing Might Fail on Receivers with Generics or Complex Types**  
   - Example:  
     ```go
     func (b Box[T]) GetValue() T { return b.value }
     ```
   - The parser may struggle to extract `T` as a return type.