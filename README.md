# gitsup
Gitsup allows automatic update of the [Git submodules](https://git-scm.com/book/en/v2/Git-Tools-Submodules) of a project to the latest commit. The intended purpose is to
deploy the tool so execution can be triggered automatically by a [Github webhook](https://developer.github.com/webhooks/) 
on update of the projects underlying the git submodules.

If the tool is executed, it will fetch the latest commit from the configured submodules and commit these changes to the 
parent repository. Git submodules that aren't configured, won't be updated.

This code is adapted from this [stackoverflow post](https://stackoverflow.com/a/51751697/3927228).

## Quickstart
- Installation: `pip install gitsup`
- Create a parent project, e.g. [tgamauf/gitsup-demo](https://github.com/tgamauf/gitsup-demo) that contains two 
submodules [tgamauf/gitsup-demo-submodule](https://github.com/tgamauf/gitsup-demo-submodule) and [jezen/is-thirteen](
https://github.com/jezen/is-thirteen) (replace the owner of the first two with your own username)
- Set the following environment variables
    - `GITSUPT_TOKEN=<Github personal access token>`
    - `GITSUPT_OWNER=tgamauf`
    - `GITSUPT_REPOSITORY=gitsup-demo`
    - `GITSUPT_SUBMODULE_gitsup-demo-submodule_OWNER=tgamauf`
- Update `README.md` in `tgamauf/gitsup-demo-submodule`
- Execute `gitsup`

Gitsup will notify you that it updated `tgamauf/gitsup-demo-submodule` in `tgamauf/gitsup-demo` and you will see a new 
commit on `tgamauf/gitsup-demo` that indicates that the submodule has been updated. The tool will also let you know 
that the submodule `is-thirteen` hasn't been updated as it isn't configured.

A config file can be provided to Gitsup by parameter `--config`. Please check the usage information for more info: `gitsup --help`

### Configuration
Configuration of gitsub can be done either by environment variables or by a yaml/json configuration file. In both cases 
a [Github personal access token](https://help.github.com/en/github/authenticating-to-github/creating-a-personal-access-token-for-the-command-line#creating-a-token), 
the parent repository and the submodules that should be auto-updated must be configured. The personal access token 
requires "repo" permissions for the parent project and all submodule projects in order to update the parent project. If 
the submodule projects are public repositories no specific permissions are required here. In any case write permissions 
for the parent repository must be granted.

The following global configuration options are available:
- token: Github access token
- owner: the owner of the parent repository
- repository: the name of the parent repository
- branch: the branch of the parent repository to update (optional; default: `master`)

For each submodule at least the repository has to be configured, for all other values sensible defaults are used if no 
value is supplied. The following configuration options exist per submodule:
- repository: the name of the submodule repository
- owner: the owner of the submodule repository (optional; default: owner of the parent project)
- branch: the branch of the submodule repository to use (optional; default: `master`)
- path: the path of the submodule in the parent repository (optional; default: repository name)

#### Environment Variables
- `GITSUPT_TOKEN=<Github personal access token>`
- `GITSUPT_OWNER=<parent repository owner>`
- `GITSUPT_REPOSITORY=<parent repository name>`
- `GITSUPT_BRANCH`=<parent repository branch>`

The following environment vairables can exist multiple times for different submodules:
- `GITSUPT_SUBMODULE_<submodule>_OWNER=<submodule repository owner>`
- `GITSUPT_SUBMODULE_<submodule>_BRANCH=<submodule repository branch>`
- `GITSUPT_SUBMODULE_<submodule>_PATH=<submodule path in parent repository>`

#### YAML Config File
```
token: <Github personal access token>
owner: <parent repository owner>
repository: <parent repository name>
branch: <parent repository branch>

submodules:
  # One dict per submodule
  <submodule>:
      owner: <submodule repository owner>
      branch: <submodule repository branch>
      path: <submodule path in parent repository>
```

#### JSON Config File
```
{
  "token": "<Github personal access token>",
  "owner": "<parent repository owner>",
  "repository": <parent repository name>,
  "branch: <parent repository branch>
  "submodules": {
    "<submodule>: {
      "owner": "<submodule repository owner>",
      "branch": "<submodule repository branch>",
      "path": "<submodule path in parent repository>"
    }
  }
}
```